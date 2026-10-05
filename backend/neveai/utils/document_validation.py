"""Independent checks on the bytes that will actually be published."""

import io
import json
import zipfile
import tempfile
from pathlib import Path

from neveai.utils.generated_files import GeneratedFileError, MAX_OUTPUT_BYTES


def validate_document_output(data: bytes, file_format: str, content: str = "") -> dict:
    fmt = file_format.lower().lstrip(".")
    if not data or len(data) > MAX_OUTPUT_BYTES:
        raise GeneratedFileError("Arquivo vazio ou maior que 32 MB.")
    report = {"validation": "passed", "checks": ["size"], "warnings": []}
    if fmt in {"docx", "xlsx", "pptx"}:
        from neveai.utils.document_edits import _office_parts, _xml

        parts = _office_parts(data)
        for name, raw in parts.items():
            if name.endswith((".xml", ".rels")):
                _xml(raw)
        expected_part = {
            "docx": "word/document.xml",
            "xlsx": "xl/workbook.xml",
            "pptx": "ppt/presentation.xml",
        }[fmt]
        if "[Content_Types].xml" not in parts or expected_part not in parts:
            raise GeneratedFileError(
                "O pacote Office nao possui a estrutura solicitada."
            )
        report["checks"].extend(["package_integrity", "xml_structure"])
        if fmt in {"xlsx", "pptx"}:
            try:
                payload = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                payload = None
            key = "sheets" if fmt == "xlsx" else "slides"
            expected = payload.get(key) if isinstance(payload, dict) else payload
            namespace = (
                "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                if fmt == "xlsx"
                else "http://schemas.openxmlformats.org/presentationml/2006/main"
            )
            tag = "sheet" if fmt == "xlsx" else "sldId"
            count = len(list(_xml(parts[expected_part]).iter(f"{{{namespace}}}{tag}")))
            if isinstance(expected, list) and expected and count != len(expected):
                raise GeneratedFileError(
                    "O arquivo gerado perdeu planilhas ou slides solicitados."
                )
            report[key] = count
            report["checks"].append("element_count")
        report["warnings"].append(
            "A estrutura foi validada; a paginacao Office nao foi renderizada por um editor externo."
        )
        from neveai.utils.officecli_files import (
            _officecli_binary,
            _run_officecli,
            OfficeCLIError,
        )

        try:
            binary = _officecli_binary()
        except OfficeCLIError:
            report["warnings"].append(
                "OfficeCLI indisponivel; validacao de schema limitada a estrutura XML."
            )
        else:
            with tempfile.TemporaryDirectory(
                prefix="neve-document-validation-"
            ) as directory:
                path = Path(directory) / ("document." + fmt)
                path.write_bytes(data)
                try:
                    result = _run_officecli(binary, "validate", str(path), "--json")
                except OfficeCLIError as error:
                    raise GeneratedFileError(
                        "A validacao Office rejeitou o arquivo: " + str(error)[:300]
                    ) from error
                diagnostics = result.get("data") or {}
                if diagnostics.get("errors") or diagnostics.get("count", 0):
                    raise GeneratedFileError(
                        "O arquivo possui erros de schema Office e nao sera publicado."
                    )
                report["checks"].append("office_schema")
                if result.get("warnings"):
                    report["warnings"].append(
                        "OfficeCLI sinalizou avisos de compatibilidade no documento."
                    )
    elif fmt == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if not reader.pages:
            raise GeneratedFileError("O PDF gerado nao possui paginas.")
        for page in reader.pages:
            if page.mediabox.width <= 0 or page.mediabox.height <= 0:
                raise GeneratedFileError("O PDF possui dimensoes de pagina invalidas.")
        report.update(pages=len(reader.pages))
        report["checks"].append("pdf_structure")
    elif fmt == "zip":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if archive.testzip() is not None:
                    raise GeneratedFileError("O ZIP gerado esta corrompido.")
            report["checks"].append("archive_integrity")
        except zipfile.BadZipFile as error:
            raise GeneratedFileError("O ZIP gerado esta corrompido.") from error
    elif fmt == "json":
        from neveai.utils.document_text import decode_document_text
        from neveai.utils.generated_files import _load_json

        _load_json(decode_document_text(data)[0], "JSON")
        report["checks"].append("json_syntax")
    elif fmt == "xml":
        from neveai.utils.document_edits import _xml

        _xml(data)
        report["checks"].append("xml_syntax")
    elif fmt in {"yaml", "yml"}:
        import yaml
        from neveai.utils.document_text import decode_document_text

        yaml.safe_load(decode_document_text(data)[0])
        report["checks"].append("yaml_syntax")
    elif fmt == "py":
        import ast
        from neveai.utils.document_text import decode_document_text

        try:
            ast.parse(data)
        except SyntaxError as error:
            raise GeneratedFileError(
                f"O Python gerado possui erro de sintaxe na linha {error.lineno}."
            ) from error
        report["checks"].append("python_syntax")
    elif fmt == "rtf":
        from neveai.utils.generated_files import read_rtf_text

        text = data.decode("ascii")
        if not text.startswith("{\\rtf1") or not text.endswith("}"):
            raise GeneratedFileError("O arquivo gerado nao e um RTF valido.")
        import re

        depth = 0
        for token in re.findall(r"\\[{}\\]|[{}]", text):
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
            if depth < 0:
                raise GeneratedFileError("O RTF possui grupos invalidos.")
        if depth:
            raise GeneratedFileError("O RTF possui grupos incompletos.")
        if content and not read_rtf_text(text).strip():
            raise GeneratedFileError("O RTF gerado perdeu seu conteudo.")
        report["checks"].append("rtf_structure")
    return report
