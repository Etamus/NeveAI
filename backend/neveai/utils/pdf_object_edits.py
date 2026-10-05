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


def _verify(data, result, expected, areas=None):
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
                if normalized_text(actual) != normalized_text(
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


def edit_pdf_pages(snapshot, edits):
    import pypdfium2 as pdfium

    expected = {snapshot.references[edit["id"]][0]: edit["new_text"] for edit in edits}
    with PDF_RENDER_LOCK:
        document = pdfium.PdfDocument(snapshot.data)
        try:
            areas = {}
            for edit in edits:
                index = snapshot.references[edit["id"]][0]
                page = document[index]
                try:
                    areas[index] = _object_edit(
                        document, page, edit["old_text"], edit["new_text"]
                    )
                finally:
                    page.close()
            output = io.BytesIO()
            document.save(output)
            result = output.getvalue()
            _verify(snapshot.data, result, expected, areas)
            return result
        except (GeneratedFileError, pdfium.PdfiumError, ValueError):
            # Reconstruct from the untouched source, never from a partly mutated PDF.
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
