"""Unicode PDF object editing, with explicit page reconstruction when necessary."""

import ctypes
import io
import re
import tempfile
from pathlib import Path

from neveai.utils.generated_files import GeneratedFileError
from neveai.utils.pdf_document_text import PDF_RENDER_LOCK, read_pdf_document


def normalized_text(text):
    return re.sub(r"\s+", " ", text).strip()


def _normalized_font_name(name):
    return re.sub(r"[^a-z0-9]", "", str(name).split("+")[-1].lower())


def inspect_pdf_pages(data, inventory, add):
    import pypdfium2 as pdfium

    missing = []
    with PDF_RENDER_LOCK:
        document = pdfium.PdfDocument(data)
        try:
            for index in range(len(document)):
                page = document[index]
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range()
                    if text.strip():
                        add(
                            f"page{index + 1}:text",
                            text,
                            (index,),
                            page=index + 1,
                            editable=True,
                        )
                    else:
                        missing.append(index)
                finally:
                    textpage.close()
                    page.close()
        finally:
            document.close()
    if missing:
        # Reuse bounded, confidence-checked OCR; never confuse unsupported fonts with a scan.
        with tempfile.TemporaryDirectory(prefix="neve-pdf-ocr-") as directory:
            path = Path(directory) / "source.pdf"
            path.write_bytes(data)
            payload = read_pdf_document(str(path))
        for index in missing:
            page = payload["pages"][index]
            if page["text"].strip():
                add(
                    f"page{index + 1}:text",
                    page["text"],
                    (index,),
                    page=index + 1,
                    editable=True,
                    ocr=True,
                )
    inventory["pdf_edit_strategy"] = "unicode_objects"


def _replacement_range(old, new):
    start = 0
    while start < min(len(old), len(new)) and old[start] == new[start]:
        start += 1
    end, new_end = len(old), len(new)
    while end > start and new_end > start and old[end - 1] == new[new_end - 1]:
        end -= 1
        new_end -= 1
    return start, end, new[start:new_end]


def _object_edit(document, page, old, new):
    import pypdfium2 as pdfium

    textpage = page.get_textpage()
    objects = list(
        page.get_objects(
            filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT], max_depth=1, textpage=textpage
        )
    )
    spans, cursor = [], 0
    try:
        if textpage.get_text_range() != old:
            raise GeneratedFileError("O texto PDF mudou desde a inspecao.")
        for obj in objects:
            text = obj.extract()
            if not text:
                continue
            start = old.find(text, cursor)
            if start < 0 or old[cursor:start].strip():
                raise GeneratedFileError("A ordem dos objetos PDF requer novo layout.")
            spans.append((start, start + len(text), obj, text))
            cursor = start + len(text)
        if old[cursor:].strip():
            raise GeneratedFileError("Texto em objetos graficos requer novo layout.")
        start, end, replacement = _replacement_range(old, new)
        affected = [span for span in spans if span[0] < end and span[1] > start]
        if start == end:
            affected = [span for span in spans if span[0] <= start < span[1]][:1]
        if not affected:
            raise GeneratedFileError("O trecho PDF precisa de novo layout.")
        first, last = affected[0], affected[-1]
        changes = []
        for span in affected:
            left, right, obj, text = span
            value = text[: max(0, start - left)] if span is first else ""
            if span is first:
                value += replacement
            if span is last:
                value += text[max(0, end - left) :]
            changes.append((obj, value))
        line_boxes = {}
        for span in affected:
            obj = span[2]
            # Include gaps between glyphs: new letters may occupy an old word's whitespace.
            line_boxes.setdefault(round(obj.get_matrix().f * 2), []).append(
                obj.get_bounds()
            )
        boxes = [
            (
                min(b[0] for b in line),
                min(b[1] for b in line),
                max(b[2] for b in line),
                max(b[3] for b in line),
            )
            for line in line_boxes.values()
        ]
    finally:
        # PDFium requires text handles to be closed before changing/removing text objects.
        textpage.close()
    for obj, value in changes:
        if not value:
            page.remove_obj(obj)
            obj.close()
        else:
            units = value.encode("utf-16-le") + b"\0\0"
            buffer = (ctypes.c_ushort * (len(units) // 2)).from_buffer_copy(units)
            if not pdfium.raw.FPDFText_SetText(obj, buffer):
                raise GeneratedFileError("A fonte PDF nao permite esta substituicao.")
            new_box = obj.get_bounds()
            region = (
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            )
            if any(
                (
                    new_box[0] < region[0] - 2,
                    new_box[1] < region[1] - 2,
                    new_box[2] > region[2] + 2,
                    new_box[3] > region[3] + 2,
                )
            ):
                raise GeneratedFileError(
                    "O novo texto requer mais espaco e novo layout."
                )
    page.gen_content()
    return boxes


def _verify(data, result, expected, areas=None, verify_text=True):
    import pypdfium2 as pdfium
    from PIL import ImageChops, ImageDraw

    first, second = pdfium.PdfDocument(data), pdfium.PdfDocument(result)
    try:
        if len(first) != len(second):
            raise GeneratedFileError("A edicao PDF alterou a quantidade de paginas.")
        for index in range(len(first)):
            before, after = first[index], second[index]
            tp_before, tp_after = before.get_textpage(), after.get_textpage()
            try:
                original = tp_before.get_text_range()
                actual = tp_after.get_text_range()
                if verify_text and normalized_text(actual) != normalized_text(
                    expected.get(index, original)
                ):
                    raise GeneratedFileError(
                        "A verificacao PDF detectou texto perdido ou alterado."
                    )
            finally:
                tp_before.close()
                tp_after.close()
            try:
                if before.get_size() != after.get_size():
                    raise GeneratedFileError(
                        "A edicao PDF alterou as dimensoes da pagina."
                    )
                # Reconstructed pages intentionally change layout; all other pages are checked.
                if areas is None and index in expected:
                    continue
                scale = min(1, 1200 / max(before.get_size()))
                a, b = before.render(scale=scale), after.render(scale=scale)
                try:
                    image_a, image_b = a.to_pil().convert("RGB"), b.to_pil().convert(
                        "RGB"
                    )
                    height = before.get_size()[1]
                    for box in (areas or {}).get(index, []):
                        rect = (
                            (box[0] - 2) * scale,
                            (height - box[3] - 2) * scale,
                            (box[2] + 2) * scale,
                            (height - box[1] + 2) * scale,
                        )
                        ImageDraw.Draw(image_a).rectangle(rect, fill="black")
                        ImageDraw.Draw(image_b).rectangle(rect, fill="black")
                    if ImageChops.difference(image_a, image_b).getbbox():
                        raise GeneratedFileError(
                            "A edicao PDF modificou a aparencia fora da area autorizada."
                        )
                finally:
                    a.close()
                    b.close()
            finally:
                before.close()
                after.close()
    finally:
        first.close()
        second.close()


def _reconstruct_pages(data, expected):
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    from pypdf import PdfReader, PdfWriter
    from neveai.utils.generated_files import configure_pdf_fonts
    import pypdfium2 as pdfium

    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter(clone_from=reader)
    sizes = {}
    document = pdfium.PdfDocument(data)
    try:
        for index in expected:
            page = document[index]
            try:
                sizes[index] = page.get_size()
            finally:
                page.close()
    finally:
        document.close()
    for index, text in expected.items():
        width, height = sizes[index]
        # Fit all text, without truncation; bounded reduction avoids illegible fallback output.
        for size in (11, 10, 9, 8):
            pdf = FPDF(unit="pt", format=(width, height))
            pdf.set_margins(36, 36, 36)
            pdf.set_auto_page_break(True, 36)
            family = configure_pdf_fonts(pdf, text)
            pdf.add_page()
            pdf.set_font(family, size=size)
            pdf.multi_cell(
                0,
                size * 1.25,
                text.replace("\r\n", "\n"),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            if len(pdf.pages) == 1:
                break
        else:
            raise GeneratedFileError(
                "O novo texto nao cabe na pagina de forma legivel; divida o pedido ou solicite novo documento."
            )
        replacement = PdfReader(io.BytesIO(bytes(pdf.output()))).pages[0]
        # Retain the original page reference for bookmarks, but remove outdated annotations/content.
        page = writer.pages[index]
        page.clear()
        page.update(replacement.clone(writer))
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _edit_literal_pdf(snapshot, edits):
    """Replace explicit text in place while retaining the original PDF page."""
    import pymupdf as fitz
    import pypdfium2 as pdfium

    document = fitz.open(stream=snapshot.data, filetype="pdf")
    areas, checks = {}, {}
    try:
        for edit in edits:
            page_index = snapshot.references[edit["id"]][0]
            page = document[page_index]
            spans = [
                span
                for block in page.get_text("dict")["blocks"]
                for line in block.get("lines", [])
                for span in line["spans"]
            ]
            page_fonts = page.get_fonts(full=True)
            font_xrefs = {font[3]: font[0] for font in page_fonts}
            jobs = []
            for replacement in edit["literal_replacements"]:
                rectangles = page.search_for(replacement["old_text"])
                if len(rectangles) != replacement["occurrences"]:
                    raise GeneratedFileError(
                        "O trecho PDF nao pode ser localizado sem ambiguidade."
                    )
                checks.setdefault(page_index, []).append(replacement)
                for rectangle in rectangles:
                    candidates = [
                        span
                        for span in spans
                        if fitz.Rect(span["bbox"]).intersects(rectangle)
                    ]
                    if not candidates:
                        raise GeneratedFileError(
                            "A formatacao do trecho PDF nao pode ser identificada."
                        )
                    span = max(
                        candidates,
                        key=lambda item: (
                            fitz.Rect(item["bbox"]) & rectangle
                        ).get_area(),
                    )
                    jobs.append((rectangle, replacement["new_text"], span, font_xrefs))
                    page.add_redact_annot(rectangle, fill=False, cross_out=False)

            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            loaded_fonts = {}
            fallback = None
            for rectangle, value, span, font_xrefs in jobs:
                font_name = span["font"]
                xref = font_xrefs.get(font_name)
                if not xref:
                    wanted = _normalized_font_name(font_name)
                    xref = next(
                        (
                            font[0]
                            for font in page_fonts
                            if wanted in _normalized_font_name(font[3])
                            or _normalized_font_name(font[3]) in wanted
                        ),
                        None,
                    )
                if not xref:
                    raise GeneratedFileError(
                        "A fonte original do PDF nao esta disponivel."
                    )
                font = loaded_fonts.get(font_name)
                if font is None:
                    buffer = document.extract_font(xref)[3]
                    font = fitz.Font(fontbuffer=buffer)
                    resource = f"NEVE{xref}"
                    page.insert_font(fontname=resource, fontbuffer=buffer)
                    loaded_fonts[font_name] = (font, resource)
                else:
                    font, resource = font
                if any(
                    not font.has_glyph(ord(char))
                    for char in value
                    if char.isascii() or char in "\u2013\u2014"
                ):
                    if fallback is None:
                        fallback_font = fitz.Font("helv")
                        fallback_resource = "NEVEFALLBACK"
                        page.insert_font(
                            fontname=fallback_resource, fontbuffer=fallback_font.buffer
                        )
                        fallback = (fallback_font, fallback_resource)
                    font, resource = fallback
                size = float(span["size"])
                width = font.text_length(value, fontsize=size)
                x = (
                    rectangle.x1 - width
                    if rectangle.x0 > page.rect.width * 0.7
                    else rectangle.x0
                )
                baseline = float(span["origin"][1])
                if x < 0 or x + width > page.rect.width:
                    raise GeneratedFileError(
                        "O novo texto nao cabe na linha original do PDF."
                    )
                page.insert_text(
                    (x, baseline),
                    value,
                    fontname=resource,
                    fontsize=size,
                    color=fitz.sRGB_to_pdf(span["color"]),
                    overlay=True,
                )
                top = baseline - size * float(span["ascender"])
                bottom = baseline - size * float(span["descender"])
                changed = fitz.Rect(
                    min(x, rectangle.x0), top, max(x + width, rectangle.x1), bottom
                )
                areas.setdefault(page_index, []).append(
                    (
                        changed.x0,
                        page.rect.height - changed.y1,
                        changed.x1,
                        page.rect.height - changed.y0,
                    )
                )

        result = document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()

    rendered = pdfium.PdfDocument(result)
    try:
        for page_index, replacements in checks.items():
            page = rendered[page_index]
            textpage = page.get_textpage()
            try:
                actual = textpage.get_text_range()
            finally:
                textpage.close()
                page.close()
            compact_actual = re.sub(r"\s+", "", actual)
            for replacement in replacements:
                compact_new = re.sub(r"\s+", "", replacement["new_text"])
                compact_old = re.sub(r"\s+", "", replacement["old_text"])
                if compact_actual.count(compact_new) < replacement["occurrences"]:
                    raise GeneratedFileError(
                        "A verificacao PDF nao encontrou todo o texto substituido."
                    )
                if compact_old not in compact_new and compact_old in compact_actual:
                    raise GeneratedFileError(
                        "A verificacao PDF encontrou texto original remanescente."
                    )
    finally:
        rendered.close()
    _verify(snapshot.data, result, {}, areas, verify_text=False)
    return result


def edit_pdf_pages(snapshot, edits):
    import pypdfium2 as pdfium

    if edits and all(edit.get("literal_replacements") for edit in edits):
        try:
            return _edit_literal_pdf(snapshot, edits)
        except (GeneratedFileError, ValueError, RuntimeError) as error:
            raise GeneratedFileError(
                "Nao foi possivel editar o PDF sem alterar seu layout; o original foi mantido intacto."
            ) from error

    expected = {snapshot.references[edit["id"]][0]: edit["new_text"] for edit in edits}
    with PDF_RENDER_LOCK:
        document = pdfium.PdfDocument(snapshot.data)
        try:
            areas = {}
            for edit in edits:
                index = snapshot.references[edit["id"]][0]
                page = document[index]
                try:
                    page_areas = areas.setdefault(index, [])
                    page_areas.extend(
                        _object_edit(document, page, edit["old_text"], edit["new_text"])
                    )
                finally:
                    page.close()
            output = io.BytesIO()
            document.save(output)
            result = output.getvalue()
            _verify(snapshot.data, result, expected, areas)
            return result
        except (GeneratedFileError, pdfium.PdfiumError, ValueError):
            # Semantic rewrites retain the existing, explicitly reported re-layout path.
            # Literal replacements are handled above and never enter this fallback.
            result = _reconstruct_pages(snapshot.data, expected)
            _verify(snapshot.data, result, expected)
            snapshot.inventory["reconstructed_pages"] = [
                index + 1 for index in sorted(expected)
            ]
            snapshot.inventory["warnings"].append(
                "O texto foi preservado, mas as paginas editadas foram reconstruidas; layout, imagens e anotacoes dessas paginas podem mudar. As outras paginas permanecem intactas."
            )
            return result
        finally:
            document.close()


def edit_simple_pdf_with_fallback(snapshot, edits):
    from dataclasses import replace

    elements, references = [], {}
    inventory = dict(snapshot.inventory, warnings=list(snapshot.inventory["warnings"]))

    def add(identifier, text, reference, **kwargs):
        elements.append({"id": identifier, "text": text, **kwargs})
        references[identifier] = reference

    inspect_pdf_pages(snapshot.data, inventory, add)
    new_texts = {item["id"]: item["text"] for item in elements}
    for edit in edits:
        page = snapshot.references[edit["id"]][0]
        identifier = f"page{page + 1}:text"
        text = new_texts.get(identifier, "")
        pattern = re.compile(
            r"\s+".join(re.escape(token) for token in edit["old_text"].split())
        )
        matches = list(pattern.finditer(text)) if edit["old_text"].strip() else []
        if len(matches) != 1:
            raise GeneratedFileError(
                "O trecho PDF nao pode ser localizado sem ambiguidade; especifique mais contexto."
            )
        start, end = matches[0].span()
        new_texts[identifier] = text[:start] + edit["new_text"] + text[end:]
    promoted = replace(
        snapshot, elements=elements, references=references, inventory=inventory
    )
    changes = [
        {"id": item["id"], "old_text": item["text"], "new_text": new_texts[item["id"]]}
        for item in elements
        if item["text"] != new_texts[item["id"]]
    ]
    result = edit_pdf_pages(promoted, changes)
    snapshot.inventory.update(inventory)
    return result
