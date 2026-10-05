import io
import unittest
from unittest.mock import AsyncMock, patch

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, ArrayObject

from neveai.utils.document_edits import (
    inspect_document,
    apply_document_edits,
    DocumentEditError,
)
from neveai.utils.document_edit_planner import (
    quoted_replacement,
    propose_document_edits,
)
from neveai.utils.generated_files import _find_unicode_font, GeneratedFileError
from neveai.utils.pdf_object_edits import normalized_text


def pdf(text="Nome: Marcos", fragmented=False):
    document = FPDF()
    document.add_font("Unicode", fname=_find_unicode_font())
    document.add_page()
    document.set_font("Unicode", size=12)
    if fragmented:
        x = 20
        for char in text:
            document.text(x, 30, char)
            x += document.get_string_width(char)
    else:
        document.text(20, 30, text)
    document.text(20, 60, "Outro trecho intacto")
    document.add_page()
    document.text(20, 30, "Segunda pagina intacta Abobora")
    return bytes(document.output())


class UnicodePdfEditsTests(unittest.TestCase):
    def edit(self, source, request='Troque "Nome: Marcos" por "Abobora"'):
        snapshot = inspect_document(source, "pdf")
        self.assertEqual(snapshot.inventory["pdf_edit_strategy"], "unicode_objects")
        changes = quoted_replacement(snapshot, request)
        result, report = apply_document_edits(snapshot, changes)
        reader = PdfReader(io.BytesIO(result))
        self.assertEqual(len(reader.pages), 2)
        self.assertIn("Abobora", reader.pages[0].extract_text())
        self.assertIn(
            "Outro trecho intacto", normalized_text(reader.pages[0].extract_text())
        )
        self.assertEqual(
            reader.pages[1].get_contents().get_data(),
            PdfReader(io.BytesIO(source)).pages[1].get_contents().get_data(),
        )
        self.assertEqual(snapshot.data, source)
        return result, report

    def test_embedded_font_keeps_other_content_and_pages(self):
        _, report = self.edit(pdf())
        self.assertNotIn("reconstructed_pages", report)

    def test_character_fragments_do_not_look_like_missing_text(self):
        _, report = self.edit(pdf(fragmented=True))
        self.assertNotIn("reconstructed_pages", report)

    def test_tj_array_is_not_ignored_when_other_text_is_simple(self):
        document = FPDF()
        document.add_page()
        document.set_font("Helvetica", size=12)
        document.text(20, 30, "Nome: Marcos")
        document.text(20, 60, "Outro trecho intacto")
        document.add_page()
        document.text(20, 30, "Segunda pagina intacta")
        reader = PdfReader(io.BytesIO(bytes(document.output())))
        writer = PdfWriter(clone_from=reader)
        stream = ContentStream(writer.pages[0].get_contents(), writer)
        for index, (args, operation) in enumerate(stream.operations):
            if operation == b"Tj":
                stream.operations[index] = ([ArrayObject([args[0]])], b"TJ")
                break
        writer.pages[0].replace_contents(stream)
        output = io.BytesIO()
        writer.write(output)
        self.edit(output.getvalue())

    def test_fallback_rebuild_is_verified_and_reported(self):
        with patch(
            "neveai.utils.pdf_object_edits._object_edit",
            side_effect=GeneratedFileError("Needs layout"),
        ):
            _, report = self.edit(pdf())
        self.assertEqual(report["reconstructed_pages"], [1])
        self.assertTrue(
            any("reconstruidas" in warning for warning in report["warnings"])
        )

    def test_missing_subset_glyph_uses_fallback_not_corrupted_letters(self):
        source = pdf()
        snapshot = inspect_document(source, "pdf")
        edits = quoted_replacement(
            snapshot, 'Troque "Nome: Marcos" por "Nova vers\u00e3o"'
        )
        data, report = apply_document_edits(snapshot, edits)
        self.assertIn(
            "Nova vers\u00e3o", PdfReader(io.BytesIO(data)).pages[0].extract_text()
        )
        self.assertEqual(report["reconstructed_pages"], [1])

    def test_rotated_page_reconstruction_preserves_display_dimensions(self):
        reader = PdfReader(io.BytesIO(pdf()))
        writer = PdfWriter(clone_from=reader)
        writer.pages[0].rotate(90)
        stream = io.BytesIO()
        writer.write(stream)
        with patch(
            "neveai.utils.pdf_object_edits._object_edit",
            side_effect=GeneratedFileError("Needs layout"),
        ):
            self.edit(stream.getvalue())

    def test_ocr_scan_has_real_editable_text(self):
        from PIL import Image, ImageDraw, ImageFont

        image = Image.new("RGB", (1200, 300), "white")
        ImageDraw.Draw(image).text(
            (50, 80),
            "Nome: Marcos",
            font=ImageFont.truetype(_find_unicode_font(), 48),
            fill="black",
        )
        document = FPDF()
        document.add_page()
        document.image(image, x=15, y=15, w=180)
        source = bytes(document.output())
        snapshot = inspect_document(source, "pdf")
        self.assertTrue(any(element.get("ocr") for element in snapshot.elements))
        edits = quoted_replacement(snapshot, 'Troque "Nome: Marcos" por "Abobora"')
        data, report = apply_document_edits(snapshot, edits)
        self.assertIn("Abobora", PdfReader(io.BytesIO(data)).pages[0].extract_text())
        self.assertEqual(report["reconstructed_pages"], [1])


class LiteralEditsTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_quote_cannot_be_routed_to_full_rewrite(self):
        from types import SimpleNamespace
        from neveai.utils.middleware import _plan_attachment_file_generation

        source = {
            "id": "test",
            "name": "document.pdf",
            "content": "Nome: Marcos",
            "metadata": {},
        }
        with (
            patch(
                "neveai.utils.middleware._get_file_generation_source_payloads",
                return_value=[source],
            ),
            patch(
                "neveai.utils.middleware.generate_chat_completion",
                new_callable=AsyncMock,
            ) as complete,
        ):
            plan = await _plan_attachment_file_generation(
                SimpleNamespace(),
                {},
                SimpleNamespace(),
                {},
                'Troque "Nome: Marcos" por "Abobora"',
                [{"id": "test"}],
                True,
            )
        self.assertEqual(plan["edit_mode"], "patch")
        self.assertEqual(plan["operation"], "edit")
        self.assertEqual(plan["source_payloads"], [source])
        complete.assert_not_awaited()

    async def test_whitespace_and_line_breaks_do_not_require_llm(self):
        snapshot = inspect_document(
            b"Antes\nNome: Marcos\nOutro trecho intacto\nDepois\n", "txt"
        )
        complete = AsyncMock()
        edits = await propose_document_edits(
            snapshot,
            'Troque o trecho inteiro "Nome:   Marcos Outro trecho intacto" por "Abobora"',
            complete,
        )
        data, _ = apply_document_edits(snapshot, edits)
        self.assertEqual(data, b"Antes\nAbobora\n\nDepois\n")
        complete.assert_not_awaited()

    def test_repeated_target_is_not_guessed(self):
        snapshot = inspect_document(b"Nome: Marcos\nNome: Marcos\n", "txt")
        with self.assertRaisesRegex(DocumentEditError, "mais de uma vez"):
            quoted_replacement(snapshot, 'Troque "Nome: Marcos" por "Abobora"')

    def test_protected_element_is_not_skipped_when_matching(self):
        snapshot = inspect_document(b"Antes\nProtegido\nDepois\n", "txt")
        snapshot.elements[1]["editable"] = False
        with self.assertRaisesRegex(DocumentEditError, "protegido"):
            quoted_replacement(
                snapshot, 'Troque "Antes Protegido Depois" por "Abobora"'
            )

    async def test_no_literal_match_still_uses_semantic_planner(self):
        snapshot = inspect_document(b"Nome: Marcos", "txt")
        complete = AsyncMock(
            return_value={
                "edits": [
                    {
                        "id": "line1",
                        "old_text": "Nome: Marcos",
                        "new_text": "Nome: Ana",
                        "value_type": "text",
                    }
                ]
            }
        )
        await propose_document_edits(snapshot, "Troque o nome por Ana", complete)
        complete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
