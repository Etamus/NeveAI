"""Bounded, optimistic edits on immutable document snapshots.

Office packages are patched directly: serializers must not drop unsupported
drawings, relationships, extensions or styles while editing a text element.
"""

import difflib
from copy import deepcopy
import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from lxml import etree

from neveai.utils.generated_files import GeneratedFileError, MAX_OUTPUT_BYTES

MAX_EXPANDED_BYTES = 128 * 1024 * 1024
MAX_ELEMENTS = 20_000
MAX_EDITS = 2_000
TEXT_FORMATS = {
    "txt",
    "md",
    "csv",
    "json",
    "html",
    "css",
    "js",
    "ts",
    "py",
    "java",
    "c",
    "cpp",
    "h",
    "sh",
    "yaml",
    "yml",
    "xml",
    "sql",
    "srt",
}
EDIT_FORMATS = {"docx", "xlsx", "pptx", "pdf", *TEXT_FORMATS}
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


class DocumentEditError(GeneratedFileError):
    pass


@dataclass
class DocumentSnapshot:
    data: bytes
    format: str
    elements: list[dict]
    inventory: dict
    references: dict
    parts: dict

    @property
    def digest(self):
        return hashlib.sha256(self.data).hexdigest()


def _xml(data):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise DocumentEditError("O documento possui entidades XML nao suportadas.")
    root = etree.fromstring(
        data, etree.XMLParser(resolve_entities=False, no_network=True)
    )
    if root.getroottree().docinfo.internalDTD is not None:
        raise DocumentEditError("O documento possui entidades XML nao suportadas.")
    return root


def _sheet_text_nodes(element):
    return element.xpath(".//s:t[not(ancestor::s:rPh)]", namespaces={"s": S})


def _office_parts(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or len(names) > 10_000:
                raise DocumentEditError(
                    "Pacote Office duplicado ou excessivamente grande."
                )
            if sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
                raise DocumentEditError(
                    "O documento excede o limite de leitura descompactada."
                )
            if any(entry.flag_bits & 1 for entry in entries):
                raise DocumentEditError(
                    "Documentos criptografados nao podem ser editados."
                )
            if any(
                PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                for name in names
            ):
                raise DocumentEditError("O pacote Office possui caminhos invalidos.")
            if any(name.startswith("_xmlsignatures/") for name in names):
                raise DocumentEditError(
                    "Editar este documento invalidaria sua assinatura digital."
                )
            return {name: archive.read(name) for name in names}
    except zipfile.BadZipFile as error:
        raise DocumentEditError("O pacote Office esta corrompido.") from error


def inspect_document(data: bytes, file_format: str) -> DocumentSnapshot:
    fmt = file_format.lower().lstrip(".")
    if fmt not in EDIT_FORMATS:
        raise DocumentEditError(
            "Este formato ainda nao suporta edicao preservando o original."
        )
    if len(data) > MAX_OUTPUT_BYTES:
        raise DocumentEditError("O documento excede o limite de 32 MB para edicao.")
    elements, references, parts = [], {}, {}
    inventory = {"format": fmt, "warnings": [], "images": 0}

    def add(identifier, text, reference, **extra):
        if len(elements) >= MAX_ELEMENTS:
            raise DocumentEditError(
                "O documento excede 20.000 elementos; divida-o antes de editar."
            )
        elements.append({"id": identifier, "text": text, **extra})
        references[identifier] = reference

    if fmt in {"docx", "pptx", "xlsx"}:
        parts = _office_parts(data)
        inventory["images"] = sum("/media/" in name for name in parts)
        if fmt in {"docx", "pptx"}:
            ns = W if fmt == "docx" else A
            pattern = (
                r"word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml"
                if fmt == "docx"
                else r"ppt/(slides/slide\d+|notesSlides/notesSlide\d+)\.xml"
            )
            for part, raw in parts.items():
                if not re.fullmatch(pattern, part):
                    continue
                root = _xml(raw)
                for index, paragraph in enumerate(root.iter(f"{{{ns}}}p")):
                    nodes = [
                        node
                        for node in paragraph.iter(f"{{{ns}}}t")
                        if next(node.iterancestors(f"{{{ns}}}p"), None) is paragraph
                    ]
                    text = "".join(node.text or "" for node in nodes)
                    if not nodes:
                        continue
                    editable = not (
                        fmt == "docx"
                        and (
                            list(paragraph.iter(f"{{{W}}}fldChar"))
                            or list(paragraph.iter(f"{{{W}}}instrText"))
                        )
                    )
                    add(
                        f"{part}:p{index}",
                        text,
                        (part, root, paragraph, nodes),
                        editable=editable,
                    )
            inventory["paragraphs"] = len(elements)
            inventory["tables"] = sum(
                len(list(_xml(raw).iter(f"{{{W if fmt == 'docx' else A}}}tbl")))
                for name, raw in parts.items()
                if name.endswith(".xml")
                and (name.startswith("word/") or name.startswith("ppt/slides/"))
            )
            inventory["warnings"].append(
                "O texto editado herda a formatacao dos trechos originais; nao ha repaginacao Office automatica."
            )
        else:
            strings = []
            if "xl/sharedStrings.xml" in parts:
                strings = [
                    "".join(node.text or "" for node in _sheet_text_nodes(item))
                    for item in _xml(parts["xl/sharedStrings.xml"]).findall(
                        f"{{{S}}}si"
                    )
                ]
            workbook = _xml(parts["xl/workbook.xml"])
            relations = {
                item.get("Id"): item.get("Target")
                for item in _xml(parts["xl/_rels/workbook.xml.rels"])
            }
            sheets = workbook.find(f"{{{S}}}sheets")
            inventory["sheets"] = len(sheets)
            inventory["formulas"] = 0
            for sheet in sheets:
                rel_id = sheet.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                target = str(relations.get(rel_id) or "")
                part = target.lstrip("/") if target.startswith("/") else "xl/" + target
                if ".." in PurePosixPath(part).parts or part not in parts:
                    raise DocumentEditError("Relacionamento de planilha nao suportado.")
                root = _xml(parts[part])
                for cell in root.iter(f"{{{S}}}c"):
                    formula, value = cell.find(f"{{{S}}}f"), cell.find(f"{{{S}}}v")
                    if formula is not None:
                        text = "=" + (formula.text or "")
                        inventory["formulas"] += 1
                    elif cell.get("t") == "s":
                        text = strings[int(value.text)] if value is not None else ""
                    elif cell.get("t") == "inlineStr":
                        text = "".join(
                            node.text or "" for node in _sheet_text_nodes(cell)
                        )
                    else:
                        text = value.text or "" if value is not None else ""
                    add(
                        f"{part}:{cell.get('r')}",
                        text,
                        (part, root, cell),
                        sheet=sheet.get("name"),
                        cell=cell.get("r"),
                        value_type=cell.get("t", "n"),
                        is_formula=formula is not None,
                        editable=not (
                            formula is not None
                            and formula.get("t") in {"array", "shared", "dataTable"}
                        ),
                    )
            inventory["warnings"].append(
                "Formulas sao preservadas e o Excel recalcula ao abrir; nao ha motor de calculo nesta edicao."
            )
    elif fmt == "pdf":
        _inspect_pdf(data, inventory, add)
    else:
        from neveai.utils.document_text import decode_document_text

        text, encoding, bom = decode_document_text(data, fmt)
        inventory.update(text_encoding=encoding, text_bom=bom.hex())
        for index, line in enumerate(text.splitlines(keepends=True)):
            add(f"line{index + 1}", line.rstrip("\r\n"), (index, line), editable=True)
        inventory["lines"] = len(elements)
    return DocumentSnapshot(data, fmt, elements, inventory, references, parts)


def inspect_document_path(path: str, file_format: str) -> DocumentSnapshot:
    source = Path(path)
    if not source.is_file() or source.stat().st_size > MAX_OUTPUT_BYTES:
        raise DocumentEditError("Arquivo indisponivel ou maior que 32 MB.")
    return inspect_document(source.read_bytes(), file_format)


def _replace_runs(nodes, old, new):
    # Map character edits back to original runs instead of flattening formatting.
    boundaries, position = [], 0
    for node in nodes:
        value = node.text or ""
        boundaries.append((position, position + len(value)))
        position += len(value)
    values = [node.text or "" for node in nodes]
    for tag, start, end, new_start, new_end in reversed(
        difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
    ):
        if tag == "equal":
            continue
        first = next(
            (i for i, (_, right) in enumerate(boundaries) if start < right),
            len(nodes) - 1,
        )
        last = next(
            (i for i, (_, right) in enumerate(boundaries) if end <= right),
            len(nodes) - 1,
        )
        last = max(first, last)
        left_offset = max(0, start - boundaries[first][0])
        right_offset = max(0, end - boundaries[last][0])
        suffix = values[last][right_offset:]
        values[first] = (
            values[first][:left_offset]
            + new[new_start:new_end]
            + (suffix if first == last else "")
        )
        for index in range(first + 1, last):
            values[index] = ""
        if first != last:
            values[last] = suffix
    for node, value in zip(nodes, values):
        node.text = value
        if value.startswith(" ") or value.endswith(" "):
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _set_cell(cell, edit, shared_strings=None):
    value_type = edit.get("value_type", "text")
    new = edit["new_text"]
    if value_type not in {"text", "number", "boolean", "formula"}:
        raise DocumentEditError("Tipo de valor de celula invalido.")
    if value_type == "number":
        try:
            if not math.isfinite(float(new)):
                raise ValueError()
        except ValueError as error:
            raise DocumentEditError("O valor numerico da celula e invalido.") from error
    if value_type == "boolean" and new not in {"0", "1"}:
        raise DocumentEditError("Booleanos de planilha devem ser 0 ou 1.")
    if value_type == "formula" and (not new.startswith("=") or len(new) < 2):
        raise DocumentEditError("A formula precisa comecar por =.")
    if value_type == "text" and cell.get("t") == "s" and shared_strings is not None:
        value = cell.find(f"{{{S}}}v")
        inline = deepcopy(shared_strings[int(value.text)])
        inline.tag = f"{{{S}}}is"
        cell.remove(value)
        cell.insert(0, inline)
        cell.set("t", "inlineStr")
    if value_type == "text" and cell.get("t") == "inlineStr":
        nodes = _sheet_text_nodes(cell)
        if nodes:
            _replace_runs(nodes, edit["old_text"], new)
            return
    for child in list(cell):
        if child.tag in {f"{{{S}}}v", f"{{{S}}}f", f"{{{S}}}is"}:
            cell.remove(child)
    if value_type == "text":
        cell.set("t", "inlineStr")
        inline = etree.Element(f"{{{S}}}is")
        text = etree.SubElement(inline, f"{{{S}}}t")
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text.text = new
        cell.insert(0, inline)
    elif value_type == "formula":
        cell.attrib.pop("t", None)
        formula = etree.Element(f"{{{S}}}f")
        formula.text = new[1:]
        cell.insert(0, formula)
    else:
        cell.set("t", "b" if value_type == "boolean" else "n")
        cell.insert(0, etree.Element(f"{{{S}}}v"))
        cell[0].text = new


def _validate_style(style, fmt):
    if not isinstance(style, dict) or not style:
        raise DocumentEditError("Informe propriedades de formatacao validas.")
    if fmt not in {"docx", "pptx"}:
        raise DocumentEditError(
            "Edicao localizada de formatacao esta disponivel para DOCX e PPTX."
        )
    if style.keys() - {
        "bold",
        "italic",
        "underline",
        "font",
        "font_size",
        "color",
        "alignment",
    }:
        raise DocumentEditError("Propriedade de formatacao nao suportada.")
    for key in ("bold", "italic", "underline"):
        if key in style and not isinstance(style[key], bool):
            raise DocumentEditError(
                "Negrito, italico e sublinhado precisam de booleanos."
            )
    if "font_size" in style and (
        isinstance(style["font_size"], bool)
        or not isinstance(style["font_size"], (int, float))
        or not 6 <= style["font_size"] <= 72
        or style["font_size"] * 2 != round(style["font_size"] * 2)
    ):
        raise DocumentEditError(
            "O tamanho de fonte deve ser de 6 a 72 pt, em intervalos de 0,5 pt."
        )
    if "font" in style and (
        not isinstance(style["font"], str)
        or not style["font"].strip()
        or len(style["font"]) > 80
        or re.search(r"[\x00-\x1f]", style["font"])
    ):
        raise DocumentEditError("Nome de fonte invalido.")
    if "color" in style and (
        not isinstance(style["color"], str)
        or not re.fullmatch(r"[0-9A-Fa-f]{6}", style["color"])
    ):
        raise DocumentEditError("Cor de fonte deve ter seis digitos hexadecimais.")
    if "alignment" in style and style["alignment"] not in {
        "left",
        "center",
        "right",
        "justify",
    }:
        raise DocumentEditError("Alinhamento de paragrafo invalido.")


def _word_run_property(props, tag):
    existing = props.find(f"{{{W}}}{tag}")
    if existing is not None:
        return existing
    order = "rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange".split()
    rank = {name: index for index, name in enumerate(order)}
    node = etree.Element(f"{{{W}}}{tag}")
    index = next(
        (
            index
            for index, child in enumerate(props)
            if rank.get(etree.QName(child).localname, len(order)) > rank[tag]
        ),
        len(props),
    )
    props.insert(index, node)
    return node


def _style_target_nodes(nodes, target, occurrence, fmt):
    if not isinstance(target, str) or not target or len(target) > 10_000:
        raise DocumentEditError("O trecho de formatacao precisa ser texto nao vazio.")
    text = "".join(node.text or "" for node in nodes)
    matches = list(re.finditer(re.escape(target), text))
    if occurrence is None and len(matches) != 1:
        raise DocumentEditError(
            "O trecho de formatacao e inexistente ou ambiguo; indique sua ocorrencia."
        )
    if occurrence is not None and (
        isinstance(occurrence, bool)
        or not isinstance(occurrence, int)
        or not 1 <= occurrence <= len(matches)
    ):
        raise DocumentEditError("Ocorrencia do trecho de formatacao invalida.")
    match = matches[(occurrence or 1) - 1]
    start, end = match.span()
    ns, position, selected = W if fmt == "docx" else A, 0, []
    for node in nodes:
        value = node.text or ""
        right = position + len(value)
        if position < end and right > start:
            run = node.getparent()
            if (
                run.tag != f"{{{ns}}}r"
                or any(child.tag not in {f"{{{ns}}}rPr", f"{{{ns}}}t"} for child in run)
                or len(run.findall(f"{{{ns}}}t")) != 1
            ):
                raise DocumentEditError(
                    "O trecho inclui objetos ou controles especiais; nao pode ser dividido sem alterar sua estrutura."
                )
            left_offset, right_offset = max(0, start - position), min(
                len(value), end - position
            )
            parent, index = run.getparent(), run.getparent().index(run)
            for fragment, marked in (
                (value[:left_offset], False),
                (value[left_offset:right_offset], True),
                (value[right_offset:], False),
            ):
                if not fragment:
                    continue
                clone = deepcopy(run)
                clone_node = clone.find(f"{{{ns}}}t")
                clone_node.text = fragment
                clone_node.set(
                    "{http://www.w3.org/XML/1998/namespace}space", "preserve"
                )
                parent.insert(index, clone)
                index += 1
                if marked:
                    selected.append(clone_node)
            parent.remove(run)
        position = right
    return selected


def _apply_text_style(paragraph, nodes, style, fmt):
    ns = W if fmt == "docx" else A
    if "alignment" in style:
        props = paragraph.find(f"{{{ns}}}pPr")
        if props is None:
            props = etree.Element(f"{{{ns}}}pPr")
            paragraph.insert(0, props)
        if fmt == "docx":
            alignment = props.find(f"{{{W}}}jc")
            if alignment is None:
                alignment = etree.Element(f"{{{W}}}jc")
                index = next(
                    (
                        index
                        for index, child in enumerate(props)
                        if etree.QName(child).localname
                        in {
                            "textDirection",
                            "textAlignment",
                            "textboxTightWrap",
                            "outlineLvl",
                            "divId",
                            "cnfStyle",
                            "rPr",
                            "sectPr",
                            "pPrChange",
                        }
                    ),
                    len(props),
                )
                props.insert(index, alignment)
            alignment.set(
                f"{{{W}}}val",
                {"justify": "both"}.get(style["alignment"], style["alignment"]),
            )
        else:
            props.set(
                "algn",
                {"left": "l", "center": "ctr", "right": "r", "justify": "just"}[
                    style["alignment"]
                ],
            )
    for run in dict.fromkeys(node.getparent() for node in nodes):
        props = run.find(f"{{{ns}}}rPr")
        if props is None:
            props = etree.Element(f"{{{ns}}}rPr")
            run.insert(0, props)
        if fmt == "docx":
            values = {
                "bold": ("b", "1" if style.get("bold") else "0"),
                "italic": ("i", "1" if style.get("italic") else "0"),
                "underline": ("u", "single" if style.get("underline") else "none"),
                "color": ("color", str(style.get("color", "")).upper()),
                "font_size": ("sz", str(round(style.get("font_size", 0) * 2))),
            }
            for key, (tag, value) in values.items():
                if key not in style:
                    continue
                node = _word_run_property(props, tag)
                node.set(f"{{{W}}}val", value)
            if "font" in style:
                fonts = _word_run_property(props, "rFonts")
                for kind in ("ascii", "hAnsi", "eastAsia", "cs"):
                    fonts.set(f"{{{W}}}{kind}", style["font"])
                    fonts.attrib.pop(f"{{{W}}}{kind}Theme", None)
        else:
            for key, attribute in (("bold", "b"), ("italic", "i")):
                if key in style:
                    props.set(attribute, "1" if style[key] else "0")
            if "underline" in style:
                props.set("u", "sng" if style["underline"] else "none")
            if "font_size" in style:
                props.set("sz", str(round(style["font_size"] * 100)))
            if "font" in style:
                latin = props.find(f"{{{A}}}latin")
                if latin is None:
                    latin = etree.Element(f"{{{A}}}latin")
                    index = next(
                        (
                            index
                            for index, child in enumerate(props)
                            if etree.QName(child).localname
                            in {
                                "ea",
                                "cs",
                                "sym",
                                "hlinkClick",
                                "hlinkMouseOver",
                                "rtl",
                                "extLst",
                            }
                        ),
                        len(props),
                    )
                    props.insert(index, latin)
                latin.set("typeface", style["font"])
            if "color" in style:
                for child in list(props):
                    if etree.QName(child).localname in {
                        "noFill",
                        "solidFill",
                        "gradFill",
                        "blipFill",
                        "pattFill",
                        "grpFill",
                    }:
                        props.remove(child)
                fill = etree.Element(f"{{{A}}}solidFill")
                etree.SubElement(fill, f"{{{A}}}srgbClr").set(
                    "val", style["color"].upper()
                )
                props.insert(
                    1 if len(props) and etree.QName(props[0]).localname == "ln" else 0,
                    fill,
                )


def apply_document_edits(
    snapshot: DocumentSnapshot, edits: list[dict]
) -> tuple[bytes, dict]:
    if not isinstance(edits, list) or not edits or len(edits) > MAX_EDITS:
        raise DocumentEditError("Informe de 1 a 2.000 alteracoes localizadas.")
    by_id = {item["id"]: item for item in snapshot.elements}
    seen = set()
    if (
        sum(
            len(str(edit.get("new_text", "")))
            for edit in edits
            if isinstance(edit, dict)
        )
        > 2_000_000
    ):
        raise DocumentEditError(
            "As alteracoes excedem 2 milhoes de caracteres por pedido."
        )
    for edit in edits:
        if not isinstance(edit, dict) or not isinstance(edit.get("new_text"), str):
            raise DocumentEditError(
                "Cada alteracao precisa de id, old_text e new_text."
            )
        identifier = edit.get("id")
        original = by_id.get(identifier)
        if not original or identifier in seen or not original.get("editable", True):
            raise DocumentEditError(
                "Alvo duplicado, protegido ou inexistente na edicao."
            )
        seen.add(identifier)
        if edit.get("old_text") != original["text"]:
            raise DocumentEditError(
                "O texto original nao corresponde ao alvo; inspecione o documento novamente."
            )
        if edit.get("style"):
            _validate_style(edit["style"], snapshot.format)
            if (
                edit.get("style_occurrence") is not None
                and edit.get("style_text") is None
            ):
                raise DocumentEditError(
                    "Uma ocorrencia de formatacao precisa especificar style_text."
                )
            if edit.get("style_text") is not None and "alignment" in edit["style"]:
                raise DocumentEditError(
                    "Alinhamento pertence ao paragrafo inteiro, nao a uma palavra."
                )
        elif (
            edit.get("style_text") is not None
            or edit.get("style_occurrence") is not None
        ):
            raise DocumentEditError(
                "Um trecho de formatacao precisa especificar style."
            )
        if edit["new_text"] == original["text"] and not edit.get("style"):
            raise DocumentEditError("A alteracao nao muda o conteudo solicitado.")
        page_edit = (
            snapshot.format == "pdf"
            and snapshot.inventory.get("pdf_edit_strategy") == "unicode_objects"
        )
        if len(edit["new_text"]) > 200_000 or (
            snapshot.format in {"docx", "pptx", "xlsx", "pdf"}
            and re.search(
                (
                    r"[\x00-\x08\x0b\x0c\x0e-\x1f]"
                    if page_edit
                    else r"[\r\n\x00-\x08\x0b\x0c\x0e-\x1f]"
                ),
                edit["new_text"],
            )
        ):
            raise DocumentEditError(
                "Texto de substituicao excessivo ou com controles nao suportados."
            )

    # Work on a fresh snapshot so failed validation never mutates the caller.
    working = inspect_document(snapshot.data, snapshot.format)
    changed_parts = {}
    if snapshot.format in {"docx", "pptx", "xlsx"}:
        shared_strings = (
            _xml(working.parts["xl/sharedStrings.xml"]).findall(f"{{{S}}}si")
            if snapshot.format == "xlsx" and "xl/sharedStrings.xml" in working.parts
            else None
        )
        for edit in edits:
            part, root, node, *rest = working.references[edit["id"]]
            # Reuse the part tree when multiple selected elements share it.
            if part in changed_parts:
                root = changed_parts[part]
                if snapshot.format == "xlsx":
                    node = next(
                        n
                        for n in root.iter(f"{{{S}}}c")
                        if n.get("r") == by_id[edit["id"]]["cell"]
                    )
                else:
                    ns = W if snapshot.format == "docx" else A
                    index = int(edit["id"].rsplit(":p", 1)[1])
                    node = list(root.iter(f"{{{ns}}}p"))[index]
                    rest = [
                        [
                            n
                            for n in node.iter(f"{{{ns}}}t")
                            if next(n.iterancestors(f"{{{ns}}}p"), None) is node
                        ]
                    ]
            if snapshot.format == "xlsx":
                _set_cell(node, edit, shared_strings)
            else:
                _replace_runs(rest[0], edit["old_text"], edit["new_text"])
                if edit.get("style"):
                    style_nodes = (
                        _style_target_nodes(
                            rest[0],
                            edit["style_text"],
                            edit.get("style_occurrence"),
                            snapshot.format,
                        )
                        if edit.get("style_text") is not None
                        else rest[0]
                    )
                    _apply_text_style(node, style_nodes, edit["style"], snapshot.format)
            changed_parts[part] = root
        if snapshot.format == "xlsx":
            workbook = _xml(working.parts["xl/workbook.xml"])
            props = workbook.find(f"{{{S}}}calcPr")
            if props is None:
                props = etree.SubElement(workbook, f"{{{S}}}calcPr")
            props.set("fullCalcOnLoad", "1")
            props.set("forceFullCalc", "1")
            changed_parts["xl/workbook.xml"] = workbook
        output = io.BytesIO()
        with (
            zipfile.ZipFile(io.BytesIO(snapshot.data)) as original,
            zipfile.ZipFile(output, "w") as archive,
        ):
            for entry in original.infolist():
                value = (
                    etree.tostring(
                        changed_parts[entry.filename],
                        xml_declaration=True,
                        encoding="UTF-8",
                        standalone=True,
                    )
                    if entry.filename in changed_parts
                    else working.parts[entry.filename]
                )
                archive.writestr(entry, value)
        data = output.getvalue()
        result_parts = _office_parts(data)
        if result_parts.keys() != snapshot.parts.keys() or any(
            result_parts[name] != raw
            for name, raw in snapshot.parts.items()
            if name not in changed_parts
        ):
            raise DocumentEditError(
                "A validacao detectou mudancas fora das partes autorizadas."
            )
    elif snapshot.format == "pdf":
        data = _edit_pdf(working, edits)
    else:
        from neveai.utils.document_text import decode_document_text

        original_text, encoding, bom = decode_document_text(
            snapshot.data, snapshot.format
        )
        lines = original_text.splitlines(keepends=True)
        default_ending = next(
            (match.group() for match in re.finditer(r"\r\n|\r|\n", original_text)), "\n"
        )
        for edit in edits:
            index, line = working.references[edit["id"]]
            ending = line[len(line.rstrip("\r\n")) :]
            lines[index] = (
                re.sub(
                    r"\r\n|\r|\n", lambda _: ending or default_ending, edit["new_text"]
                )
                + ending
            )
        expected_text = "".join(lines)
        from neveai.utils.document_text import encode_edited_text

        data, expected_text, encoding_warning = encode_edited_text(
            expected_text, encoding, bom, snapshot.format
        )
        if encoding_warning:
            working.inventory["warnings"].append(encoding_warning)
        if snapshot.format == "json":
            from neveai.utils.generated_files import _load_json

            _load_json(expected_text, "JSON")
        if snapshot.format == "xml":
            _xml(data)

    if len(data) > MAX_OUTPUT_BYTES:
        raise DocumentEditError("O arquivo editado excede 32 MB.")
    result = inspect_document(data, snapshot.format)
    after = {element["id"]: element for element in result.elements}
    if snapshot.format in TEXT_FORMATS:
        if decode_document_text(data, snapshot.format)[0] != expected_text:
            raise DocumentEditError(
                "O arquivo de texto nao preservou o conteudo esperado."
            )
    elif snapshot.format != "pdf":
        if after.keys() != by_id.keys():
            raise DocumentEditError(
                "A edicao alterou a estrutura de elementos do documento."
            )
        expected = {edit["id"]: edit["new_text"] for edit in edits}
        for identifier, before in by_id.items():
            if after[identifier]["text"] != expected.get(identifier, before["text"]):
                raise DocumentEditError(
                    "A verificacao de conteudo detectou uma alteracao inesperada."
                )
    preview = [
        {
            "id": edit["id"],
            "old_text": edit["old_text"][:200],
            "new_text": edit["new_text"][:200],
            **({"style": edit["style"]} if edit.get("style") else {}),
            **(
                {"style_text": edit["style_text"]}
                if edit.get("style_text") is not None
                else {}
            ),
        }
        for edit in edits[:20]
    ]
    truncated = len(edits) > 20 or any(
        len(edit[key]) > 200 for edit in edits for key in ("old_text", "new_text")
    )
    return data, {
        "source_sha256": snapshot.digest,
        "output_sha256": result.digest,
        "changed_elements": len(edits),
        "changed_parts": list(changed_parts),
        "validation": "passed",
        "warnings": working.inventory["warnings"],
        **(
            {"reconstructed_pages": working.inventory["reconstructed_pages"]}
            if working.inventory.get("reconstructed_pages")
            else {}
        ),
        "change_preview": preview,
        "preview_truncated": truncated,
    }


PDF_CORE_FONTS = {
    "/Helvetica": "helvetica",
    "/Helvetica-Bold": "helveticaB",
    "/Helvetica-Oblique": "helveticaI",
    "/Helvetica-BoldOblique": "helveticaBI",
    "/Times-Roman": "times",
    "/Times-Bold": "timesB",
    "/Times-Italic": "timesI",
    "/Times-BoldItalic": "timesBI",
    "/Courier": "courier",
    "/Courier-Bold": "courierB",
    "/Courier-Oblique": "courierI",
    "/Courier-BoldOblique": "courierBI",
}


def _pdf_width(text, font, size):
    from fpdf.fonts import CORE_FONTS_CHARWIDTHS

    try:
        encoded = text.encode("cp1252")
    except UnicodeEncodeError as error:
        raise DocumentEditError(
            "A fonte deste PDF nao suporta os caracteres solicitados."
        ) from error
    widths = CORE_FONTS_CHARWIDTHS[font]
    return sum(widths.get(chr(char), 1000) for char in encoded) * size / 1000


def _inspect_pdf(data, inventory, add):
    tentative = []
    _inspect_simple_pdf(
        data, inventory, lambda *args, **kwargs: tentative.append((args, kwargs))
    )
    if (
        tentative
        and not inventory.get("pdf_needs_unicode")
        and all(kwargs.get("editable") for _, kwargs in tentative)
    ):
        for args, kwargs in tentative:
            add(*args, **kwargs)
        return
    from neveai.utils.pdf_object_edits import inspect_pdf_pages

    inventory["warnings"] = [
        "PDF: fontes incorporadas e texto fragmentado usam edicao de objetos Unicode; paginas que exigirem novo layout serao sinalizadas."
    ]
    inspect_pdf_pages(data, inventory, add)


def _inspect_simple_pdf(data, inventory, add):
    from pypdf import PdfReader
    from pypdf.generic import ContentStream, TextStringObject, ByteStringObject

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise DocumentEditError("PDF protegido por senha nao pode ser editado.")
    if len(reader.pages) > 200:
        raise DocumentEditError("A edicao PDF suporta ate 200 paginas por pedido.")
    inventory.update(pages=len(reader.pages), scanned_pages=[])
    for number, page in enumerate(reader.pages):
        fonts = page.get("/Resources", {}).get("/Font", {})
        xobjects = page.get("/Resources", {}).get("/XObject", {})
        has_forms = any(
            item.get_object().get("/Subtype") == "/Form" for item in xobjects.values()
        )
        inventory["images"] += sum(
            item.get_object().get("/Subtype") == "/Image" for item in xobjects.values()
        )
        if not page.extract_text().strip():
            inventory["scanned_pages"].append(number + 1)
            inventory["pdf_needs_unicode"] = True
        stream = (
            ContentStream(page.get_contents(), reader)
            if page.get_contents() is not None
            else None
        )
        if has_forms or (
            stream is not None
            and any(op in {b"TJ", b"'", b'"'} for _, op in stream.operations)
        ):
            inventory["pdf_needs_unicode"] = True
        font, size, operation_index = None, 0, -1
        spacing_safe = True

        def visitor(operator, operands, cm, tm):
            nonlocal font, size, operation_index, spacing_safe
            operation_index += 1
            if operator == b"Tf":
                font, size = fonts.get(operands[0]), float(operands[1])
                font = font.get_object() if font is not None else None
            elif operator in {b"Tc", b"Tw"} and operands:
                spacing_safe = spacing_safe and float(operands[0]) == 0
            elif operator == b"Tz" and operands:
                spacing_safe = spacing_safe and float(operands[0]) == 100
            if (
                operator != b"Tj"
                or not operands
                or not isinstance(operands[0], (TextStringObject, ByteStringObject))
            ):
                return
            base = str(font.get("/BaseFont", "")) if font else ""
            encoding = font.get("/Encoding") if font else None
            editable = (
                not has_forms
                and page.rotation == 0
                and base in PDF_CORE_FONTS
                and (
                    encoding is None
                    or isinstance(encoding, str)
                    and encoding == "/WinAnsiEncoding"
                )
                and spacing_safe
                and list(cm[:4]) == [1, 0, 0, 1]
                and list(tm[:4]) == [1, 0, 0, 1]
            )
            value = operands[0]
            text = (
                value.original_bytes
                if isinstance(value, TextStringObject)
                else bytes(value)
            ).decode("cp1252", errors="replace")
            if not text.strip():
                return
            metrics = PDF_CORE_FONTS.get(base)
            x, y = cm[4] + tm[4], cm[5] + tm[5]
            width = _pdf_width(text, metrics, size) if metrics else 0
            box = [
                x,
                float(page.mediabox.height) - y - size * 1.2,
                x + width,
                float(page.mediabox.height) - y + size * 0.35,
            ]
            add(
                f"page{number + 1}:op{operation_index}",
                text,
                (number, operation_index, metrics, size, box, stream),
                page=number + 1,
                editable=editable,
            )

        page.extract_text(visitor_operand_before=visitor)
    inventory["warnings"].append(
        "PDF: edicao local apenas de texto simples com fonte padrao, sem rotacao, que caiba no mesmo espaco. Outros casos requerem novo layout."
    )


def _edit_pdf(snapshot, edits):
    from neveai.utils.pdf_document_text import PDF_RENDER_LOCK

    with PDF_RENDER_LOCK:
        if snapshot.inventory.get("pdf_edit_strategy") == "unicode_objects":
            from neveai.utils.pdf_object_edits import edit_pdf_pages

            return edit_pdf_pages(snapshot, edits)
        try:
            return _edit_pdf_locked(snapshot, edits)
        except DocumentEditError:
            from neveai.utils.pdf_object_edits import edit_simple_pdf_with_fallback

            return edit_simple_pdf_with_fallback(snapshot, edits)


def _edit_pdf_locked(snapshot, edits):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ByteStringObject, ContentStream
    import pypdfium2 as pdfium
    from PIL import ImageDraw, ImageChops

    reader = PdfReader(io.BytesIO(snapshot.data))
    writer = PdfWriter(clone_from=reader)
    streams, areas = {}, {}
    for edit in edits:
        number, operation, font, size, box, _ = snapshot.references[edit["id"]]
        if _pdf_width(edit["new_text"], font, size) > box[2] - box[0] + 0.5:
            raise DocumentEditError(
                "O novo texto nao cabe na area original do PDF; use reescrita com novo layout."
            )
        stream = streams.setdefault(
            number, ContentStream(writer.pages[number].get_contents(), writer)
        )
        stream.operations[operation][0][0] = ByteStringObject(
            edit["new_text"].encode("cp1252")
        )
        areas.setdefault(number, []).append(box)
    for number, stream in streams.items():
        writer.pages[number].replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    data = output.getvalue()
    after_snapshot = inspect_document(data, "pdf")
    after = {item["id"]: item["text"] for item in after_snapshot.elements}
    expected = {edit["id"]: edit["new_text"] for edit in edits}
    for before in snapshot.elements:
        if not expected.get(before["id"], before["text"]):
            continue
        if after.get(before["id"]) != expected.get(before["id"], before["text"]):
            raise DocumentEditError("A edicao PDF nao preservou o texto esperado.")
    after_reader = PdfReader(io.BytesIO(data))
    original_pdf, result_pdf = pdfium.PdfDocument(snapshot.data), pdfium.PdfDocument(
        data
    )
    try:
        for index in range(len(original_pdf)):
            if index not in areas:
                before_stream = reader.pages[index].get_contents()
                after_stream = after_reader.pages[index].get_contents()
                if reader.pages[index].mediabox != after_reader.pages[
                    index
                ].mediabox or (before_stream.get_data() if before_stream else b"") != (
                    after_stream.get_data() if after_stream else b""
                ):
                    raise DocumentEditError(
                        "A edicao alterou o conteudo de uma pagina nao selecionada."
                    )
                continue
            before_page, after_page = original_pdf[index], result_pdf[index]
            bitmap_before = bitmap_after = None
            try:
                if before_page.get_size() != after_page.get_size():
                    raise DocumentEditError(
                        "A edicao alterou as dimensoes da pagina PDF."
                    )
                width, height = before_page.get_size()
                scale = min(1, 1600 / max(width, height))
                bitmap_before, bitmap_after = before_page.render(
                    scale=scale
                ), after_page.render(scale=scale)
                first, second = bitmap_before.to_pil().convert(
                    "RGB"
                ), bitmap_after.to_pil().convert("RGB")
                for box in areas.get(index, []):
                    mask = tuple(
                        (value + (-2 if i < 2 else 2)) * scale
                        for i, value in enumerate(box)
                    )
                    ImageDraw.Draw(first).rectangle(mask, fill="black")
                    ImageDraw.Draw(second).rectangle(mask, fill="black")
                if ImageChops.difference(first, second).getbbox() is not None:
                    raise DocumentEditError(
                        "A edicao modificou pixels fora do trecho autorizado do PDF."
                    )
            finally:
                if bitmap_before:
                    bitmap_before.close()
                if bitmap_after:
                    bitmap_after.close()
                before_page.close()
                after_page.close()
    finally:
        original_pdf.close()
        result_pdf.close()
    return data
