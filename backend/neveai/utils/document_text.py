"""Decode document text without replacing undecodable bytes or losing its BOM."""

from neveai.utils.generated_files import GeneratedFileError
import re


def decode_document_text(data, file_format=None):
    for bom, encoding in (
        (b"\xff\xfe\0\0", "utf-32-le"),
        (b"\0\0\xfe\xff", "utf-32-be"),
        (b"\xef\xbb\xbf", "utf-8"),
        (b"\xff\xfe", "utf-16-le"),
        (b"\xfe\xff", "utf-16-be"),
    ):
        if data.startswith(bom):
            try:
                return data[len(bom) :].decode(encoding), encoding, bom
            except UnicodeDecodeError as error:
                raise GeneratedFileError(
                    "O arquivo tem codificacao declarada, mas contem bytes invalidos."
                ) from error
    declared = None
    if file_format == "xml":
        match = re.match(
            rb'\s*<\?xml\b[^>]*\bencoding\s*=\s*["\']([^"\']+)', data[:512], re.I
        )
        if match:
            declared = match.group(1).decode("ascii")
    elif file_format == "py":
        import io
        import tokenize

        try:
            declared, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        except SyntaxError:
            pass
    if declared:
        import codecs

        try:
            encoding = codecs.lookup(declared).name
            if encoding not in {"utf-8", "ascii", "cp1252", "iso8859-1"}:
                raise GeneratedFileError(
                    "A codificacao declarada precisa ser UTF-8, Latin-1 ou Windows-1252, ou UTF-16/32 com BOM."
                )
            return data.decode(encoding), encoding, b""
        except (LookupError, UnicodeDecodeError) as error:
            raise GeneratedFileError(
                "A codificacao declarada nao corresponde aos bytes do documento."
            ) from error
    try:
        text, encoding = data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        try:
            text, encoding = data.decode("cp1252"), "cp1252"
        except UnicodeDecodeError as error:
            raise GeneratedFileError(
                "A codificacao do documento nao pode ser lida sem perder caracteres."
            ) from error
    if "\0" in text:
        raise GeneratedFileError(
            "O anexo parece binario ou UTF-16 sem identificacao; envie texto com BOM."
        )
    return text, encoding, b""


def encode_edited_text(text, encoding, bom, file_format):
    upgrade = file_format == "py" and encoding.startswith(("utf-16", "utf-32"))
    if not upgrade:
        try:
            return bom + text.encode(encoding), text, None
        except UnicodeEncodeError:
            upgrade = True
    if upgrade:
        if file_format == "xml":
            text = re.sub(
                r'(<\?xml\b[^>]*\bencoding\s*=\s*["\'])[^"\']+(["\'])',
                r"\1UTF-8\2",
                text,
                count=1,
                flags=re.I,
            )
        elif file_format == "py":
            lines = text.splitlines(keepends=True)
            for index in range(min(2, len(lines))):
                if lines[index].lstrip().startswith("#"):
                    lines[index] = re.sub(
                        r"coding[:=]\s*[-\w.]+", "coding: utf-8", lines[index]
                    )
            text = "".join(lines)
        return (
            b"\xef\xbb\xbf" + text.encode("utf-8"),
            text,
            "A codificacao foi convertida para UTF-8 com BOM para manter os caracteres e a compatibilidade do formato.",
        )
