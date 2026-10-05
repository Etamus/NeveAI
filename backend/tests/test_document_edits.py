import asyncio
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from lxml import etree

from neveai.utils.document_edits import (
    DocumentEditError,
    apply_document_edits,
    inspect_document,
    _replace_runs,
)
from neveai.utils.document_edit_planner import element_batches, propose_document_edits


def saved(document):
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def replacement(snapshot, old, new, **extra):
    element = next(item for item in snapshot.elements if item["text"] == old)
    return {"id": element["id"], "old_text": old, "new_text": new, **extra}


class PreservingOfficeEditsTests(unittest.TestCase):
    def test_paragraph_style_changes_keep_text_other_runs_and_schema(self):
        from docx import Document
        from pptx import Presentation
        from neveai.utils.document_validation import validate_document_output

        document = Document()
        document.add_paragraph("Titulo")
        document.add_paragraph("Manter o restante")
        presentation = Presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[5])
        slide.shapes.title.text = "Titulo"
        for fmt, original in [("docx", document), ("pptx", presentation)]:
            snapshot = inspect_document(saved(original), fmt)
            edit = replacement(
                snapshot,
                "Titulo",
                "Titulo",
                style={
                    "bold": True,
                    "italic": True,
                    "underline": True,
                    "font": "Arial",
                    "font_size": 16.5,
                    "color": "FF0000",
                    "alignment": "center",
                },
            )
            data, _ = apply_document_edits(snapshot, [edit])
            validate_document_output(data, fmt)
            if fmt == "docx":
                after = Document(io.BytesIO(data))
                self.assertTrue(after.paragraphs[0].runs[0].bold)
                self.assertEqual(after.paragraphs[0].runs[0].font.size.pt, 16.5)
                self.assertEqual(after.paragraphs[1].text, "Manter o restante")
                self.assertIsNone(after.paragraphs[1].runs[0].bold)
            else:
                after = Presentation(io.BytesIO(data))
                run = after.slides[0].shapes.title.text_frame.paragraphs[0].runs[0]
                self.assertTrue(run.font.bold)
                self.assertEqual(run.font.size.pt, 16.5)
                self.assertEqual(after.slides[0].shapes.title.text, "Titulo")

    def test_shared_rich_text_cell_does_not_change_other_cells_or_font(self):
        from openpyxl import Workbook
        from neveai.utils.document_edits import S

        workbook = Workbook()
        workbook.active.append(["Marcos", "Marcos"])
        data = saved(workbook)
        with zipfile.ZipFile(io.BytesIO(data)) as source:
            parts = {name: source.read(name) for name in source.namelist()}
        part = "xl/worksheets/sheet1.xml"
        root = etree.fromstring(parts[part])
        for cell in root.iter(f"{{{S}}}c"):
            for child in list(cell):
                cell.remove(child)
            cell.set("t", "s")
            etree.SubElement(cell, f"{{{S}}}v").text = "0"
        parts[part] = etree.tostring(root)
        parts["xl/sharedStrings.xml"] = (
            f'<sst xmlns="{S}" count="2" uniqueCount="1"><si><r><rPr><b/></rPr><t>Mar</t></r><r><t>cos</t></r></si></sst>'.encode()
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, raw in parts.items():
                archive.writestr(name, raw)
        snapshot = inspect_document(output.getvalue(), "xlsx")
        element = next(item for item in snapshot.elements if item["cell"] == "A1")
        data, _ = apply_document_edits(
            snapshot,
            [
                {
                    "id": element["id"],
                    "old_text": "Marcos",
                    "new_text": "Mateus",
                    "value_type": "text",
                }
            ],
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            result = etree.fromstring(archive.read(part))
            self.assertEqual(
                archive.read("xl/sharedStrings.xml"), parts["xl/sharedStrings.xml"]
            )
            self.assertTrue(
                result.xpath("//s:c[@r='A1']/s:is/s:r/s:rPr/s:b", namespaces={"s": S})
            )
        elements = inspect_document(data, "xlsx").elements
        self.assertEqual(
            next(item["text"] for item in elements if item["cell"] == "B1"), "Marcos"
        )

    def test_run_mapping_randomized_replacements(self):
        import random

        rng = random.Random(42)
        for _ in range(500):
            old = "".join(rng.choice("abc def") for _ in range(rng.randint(0, 30)))
            new = "".join(rng.choice("abc def") for _ in range(rng.randint(0, 30)))
            split = sorted([0, len(old), *[rng.randint(0, len(old)) for _ in range(4)]])
            nodes = [etree.Element("t") for _ in range(len(split) - 1)]
            for index, node in enumerate(nodes):
                node.text = old[split[index] : split[index + 1]]
            _replace_runs(nodes, old, new)
            self.assertEqual("".join(node.text or "" for node in nodes), new)

    def docx_fixture(self):
        from docx import Document

        document = Document()
        paragraph = document.add_paragraph()
        paragraph.add_run("Nome: ").bold = True
        paragraph.add_run("Marcos").italic = True
        paragraph.add_run(" - manter").underline = True
        document.add_paragraph("Nao alterar este paragrafo.")
        document.add_table(rows=1, cols=2).cell(0, 0).text = "Marcos"
        document.sections[0].header.paragraphs[0].text = "Cabecalho preservado"
        document.sections[0].footer.paragraphs[0].text = "Rodape preservado"
        from PIL import Image

        image = io.BytesIO()
        Image.new("RGB", (20, 20), "red").save(image, format="PNG")
        image.seek(0)
        document.add_picture(image)
        return saved(document)

    def test_docx_preserves_runs_headers_images_tables_and_original(self):
        from docx import Document

        data = self.docx_fixture()
        snapshot = inspect_document(data, "docx")
        edits = [
            replacement(snapshot, "Nome: Marcos - manter", "Nome: Mateus - manter")
        ]
        result, report = apply_document_edits(snapshot, edits)
        document = Document(io.BytesIO(result))
        self.assertEqual(document.paragraphs[0].text, "Nome: Mateus - manter")
        self.assertEqual(
            [run.text for run in document.paragraphs[0].runs],
            ["Nome: ", "Mateus", " - manter"],
        )
        self.assertTrue(document.paragraphs[0].runs[0].bold)
        self.assertTrue(document.paragraphs[0].runs[1].italic)
        self.assertTrue(document.paragraphs[0].runs[2].underline)
        self.assertEqual(document.tables[0].cell(0, 0).text, "Marcos")
        self.assertEqual(len(document.inline_shapes), 1)
        self.assertEqual(snapshot.data, data)
        self.assertEqual(snapshot.elements[0]["text"], "Nome: Marcos - manter")
        self.assertEqual(report["validation"], "passed")
        with (
            zipfile.ZipFile(io.BytesIO(data)) as before,
            zipfile.ZipFile(io.BytesIO(result)) as after,
        ):
            for name in before.namelist():
                if name != "word/document.xml":
                    self.assertEqual(before.read(name), after.read(name), name)

    def test_docx_multiple_targets_same_part_and_header(self):
        snapshot = inspect_document(self.docx_fixture(), "docx")
        edits = [
            replacement(snapshot, "Nome: Marcos - manter", "Nome: Ana - manter"),
            replacement(snapshot, "Nao alterar este paragrafo.", "Paragrafo revisado."),
            replacement(snapshot, "Cabecalho preservado", "Cabecalho revisado"),
        ]
        data, _ = apply_document_edits(snapshot, edits)
        result = inspect_document(data, "docx")
        self.assertIn("Cabecalho revisado", [item["text"] for item in result.elements])

    def test_xlsx_preserves_formulas_styles_merge_chart_validation(self):
        from openpyxl import Workbook, load_workbook
        from openpyxl.chart import BarChart, Reference
        from openpyxl.styles import Font
        from openpyxl.worksheet.datavalidation import DataValidation

        document = Workbook()
        sheet = document.active
        sheet.title = "Dados"
        sheet.append(["Nome", "Valor", "Formula"])
        sheet.append(["Marcos", 10, "=B2*2"])
        sheet["A2"].font = Font(bold=True, color="FF0000")
        sheet.merge_cells("A4:B4")
        chart = BarChart()
        chart.add_data(
            Reference(sheet, min_col=2, min_row=1, max_row=2), titles_from_data=True
        )
        sheet.add_chart(chart, "E1")
        validation = DataValidation(
            type="whole", operator="between", formula1=0, formula2=100
        )
        validation.add("B2")
        sheet.add_data_validation(validation)
        snapshot = inspect_document(saved(document), "xlsx")
        data, _ = apply_document_edits(
            snapshot,
            [
                replacement(snapshot, "Marcos", "Mateus"),
                replacement(snapshot, "10", "20", value_type="number"),
            ],
        )
        workbook = load_workbook(io.BytesIO(data))
        sheet = workbook.active
        self.assertEqual(sheet["A2"].value, "Mateus")
        self.assertEqual(sheet["B2"].value, 20)
        self.assertEqual(sheet["C2"].value, "=B2*2")
        self.assertTrue(sheet["A2"].font.bold)
        self.assertEqual(len(sheet._charts), 1)
        self.assertEqual(len(sheet.data_validations.dataValidation), 1)
        self.assertIn("A4:B4", str(sheet.merged_cells))
        self.assertTrue(workbook.calculation.fullCalcOnLoad)
        workbook.close()

    def test_xlsx_formula_is_explicit_and_text_is_not_formula_injection(self):
        from openpyxl import Workbook, load_workbook

        document = Workbook()
        document.active.append(["original", "=1+1"])
        snapshot = inspect_document(saved(document), "xlsx")
        data, _ = apply_document_edits(
            snapshot,
            [
                replacement(
                    snapshot,
                    "original",
                    '=HYPERLINK("https://example.com")',
                    value_type="text",
                ),
                replacement(snapshot, "=1+1", "=2+2", value_type="formula"),
            ],
        )
        result = load_workbook(io.BytesIO(data))
        self.assertEqual(result.active["A1"].data_type, "s")
        self.assertEqual(result.active["B1"].data_type, "f")
        result.close()

    def test_pptx_preserves_slide_shapes_picture_table_and_font(self):
        from pptx import Presentation
        from pptx.util import Inches
        from PIL import Image

        document = Presentation()
        slide = document.slides.add_slide(document.slide_layouts[5])
        slide.shapes.title.text = "Titulo original"
        slide.shapes.title.text_frame.paragraphs[0].runs[0].font.bold = True
        table = slide.shapes.add_table(
            1, 2, Inches(1), Inches(2), Inches(4), Inches(1)
        ).table
        table.cell(0, 0).text = "Tabela mantida"
        image = io.BytesIO()
        Image.new("RGB", (20, 20), "blue").save(image, format="PNG")
        image.seek(0)
        slide.shapes.add_picture(image, Inches(6), Inches(1))
        snapshot = inspect_document(saved(document), "pptx")
        data, _ = apply_document_edits(
            snapshot, [replacement(snapshot, "Titulo original", "Titulo revisado")]
        )
        after = Presentation(io.BytesIO(data))
        self.assertEqual(len(after.slides[0].shapes), len(slide.shapes))
        self.assertTrue(
            after.slides[0].shapes.title.text_frame.paragraphs[0].runs[0].font.bold
        )
        self.assertEqual(after.slides[0].shapes.title.text, "Titulo revisado")

    def test_run_edits_across_boundaries_insert_delete_and_repeat(self):
        cases = [
            ("abcdef", "abXYef"),
            ("abcabc", "abZabc"),
            ("abc", "XabcY"),
            ("abc", ""),
            ("aaaaa", "aaXaa"),
            ("", "novo"),
        ]
        for old, new in cases:
            nodes = [etree.Element("t") for _ in range(3)]
            nodes[0].text, nodes[1].text, nodes[2].text = old[:2], old[2:4], old[4:]
            _replace_runs(nodes, old, new)
            self.assertEqual("".join(node.text or "" for node in nodes), new)

    def test_guards_unknown_duplicate_stale_noop_newlines(self):
        snapshot = inspect_document(self.docx_fixture(), "docx")
        valid = replacement(snapshot, "Nome: Marcos - manter", "Nome: Ana - manter")
        for edits in [
            [{**valid, "id": "missing"}],
            [valid, valid],
            [{**valid, "old_text": "wrong"}],
            [{**valid, "new_text": valid["old_text"]}],
            [{**valid, "new_text": "quebra\nlinha"}],
            [],
        ]:
            with self.assertRaises(DocumentEditError):
                apply_document_edits(snapshot, edits)

    def test_unknown_parts_are_preserved_and_entities_rejected(self):
        original = self.docx_fixture()
        output = io.BytesIO()
        with (
            zipfile.ZipFile(io.BytesIO(original)) as source,
            zipfile.ZipFile(output, "w") as archive,
        ):
            for item in source.infolist():
                archive.writestr(item, source.read(item.filename))
            archive.writestr("customXml/neve-extension.bin", b"do not discard")
        snapshot = inspect_document(output.getvalue(), "docx")
        data, _ = apply_document_edits(
            snapshot,
            [replacement(snapshot, "Nome: Marcos - manter", "Nome: Ana - manter")],
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(
                archive.read("customXml/neve-extension.bin"), b"do not discard"
            )


class TextAndPdfEditsTests(unittest.TestCase):
    def test_utf8_bom_crlf_and_unselected_bytes(self):
        source = b"\xef\xbb\xbfNome: Marcos\r\nManter\r\n"
        snapshot = inspect_document(source, "txt")
        data, _ = apply_document_edits(
            snapshot, [replacement(snapshot, "Nome: Marcos", "Nome: Mateus")]
        )
        self.assertEqual(data, b"\xef\xbb\xbfNome: Mateus\r\nManter\r\n")

    def test_invalid_json_cannot_be_published(self):
        snapshot = inspect_document(b'{"name":"Marcos"}', "json")
        with self.assertRaises(ValueError):
            apply_document_edits(
                snapshot, [replacement(snapshot, '{"name":"Marcos"}', "invalid")]
            )

    def pdf(self):
        from fpdf import FPDF

        document = FPDF()
        document.add_page()
        document.set_font("Helvetica", size=12)
        document.text(20, 30, "Nome: Marcos")
        document.text(20, 50, "Texto mantido")
        document.add_page()
        document.text(20, 30, "Pagina mantida")
        return bytes(document.output())

    def test_pdf_local_edit_keeps_other_pixels_and_original(self):
        from pypdf import PdfReader

        source = self.pdf()
        snapshot = inspect_document(source, "pdf")
        data, report = apply_document_edits(
            snapshot, [replacement(snapshot, "Nome: Marcos", "Nome: Ana")]
        )
        reader = PdfReader(io.BytesIO(data))
        self.assertIn("Nome: Ana", reader.pages[0].extract_text())
        self.assertIn("Texto mantido", reader.pages[0].extract_text())
        self.assertEqual(len(reader.pages), 2)
        self.assertEqual(source, snapshot.data)
        self.assertEqual(report["validation"], "passed")

    def test_pdf_long_replacement_reconstructs_without_clipping(self):
        snapshot = inspect_document(self.pdf(), "pdf")
        new = "Um texto muito longo que nao cabe no espaco original " * 5
        data, report = apply_document_edits(
            snapshot, [replacement(snapshot, "Nome: Marcos", new)]
        )
        from pypdf import PdfReader
        from neveai.utils.pdf_object_edits import normalized_text

        text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
        self.assertIn(normalized_text(new), normalized_text(text))
        self.assertIn("Texto mantido", text)
        self.assertEqual(report["reconstructed_pages"], [1])


class DocumentPlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_style_repair_does_not_publish_markdown_or_change_words(self):
        from docx import Document

        document = Document()
        document.add_paragraph("Nome: Marcos")
        stream = io.BytesIO()
        document.save(stream)
        snapshot = inspect_document(stream.getvalue(), "docx")
        complete = AsyncMock(
            side_effect=[
                {
                    "edits": [
                        replacement(
                            snapshot,
                            "Nome: Marcos",
                            "**Nome: Marcos**",
                            value_type="text",
                        )
                    ]
                },
                {
                    "edits": [
                        replacement(
                            snapshot,
                            "Nome: Marcos",
                            "Nome: Marcos",
                            value_type="text",
                            style={"bold": True},
                        )
                    ]
                },
            ]
        )
        edits = await propose_document_edits(
            snapshot, "Deixe em negrito, nao troque nenhuma palavra", complete
        )
        self.assertEqual(complete.await_count, 2)
        repair = json.loads(complete.await_args_list[1].args[0][1]["content"])
        self.assertIn("style", repair["repair_issue"])
        data, _ = apply_document_edits(snapshot, edits)
        result = Document(io.BytesIO(data))
        self.assertEqual(result.paragraphs[0].text, "Nome: Marcos")
        self.assertTrue(result.paragraphs[0].runs[0].bold)

    async def test_portuguese_objective_exact_edits(self):
        snapshot = inspect_document(b"Nome: Marcos\nNao alterar\n", "txt")

        async def complete(messages, schema):
            request = json.loads(messages[1]["content"])
            self.assertEqual(
                request["objective"], "Troque Marcos por Mateus, mantenha o resto"
            )
            return {
                "edits": [
                    replacement(
                        snapshot, "Nome: Marcos", "Nome: Mateus", value_type="text"
                    )
                ]
            }

        edits = await propose_document_edits(
            snapshot, "Troque Marcos por Mateus, mantenha o resto", complete
        )
        self.assertEqual(len(edits), 1)

    async def test_repair_bad_ids_and_fail_after_two_attempts(self):
        snapshot = inspect_document(b"Nome: Marcos", "txt")
        complete = AsyncMock(
            return_value={
                "edits": [{"id": "missing", "old_text": "Marcos", "new_text": "Ana"}]
            }
        )
        with self.assertRaises(DocumentEditError):
            await propose_document_edits(snapshot, "Troque o nome", complete)
        self.assertEqual(complete.await_count, 2)

    async def test_no_change_is_explicit_not_silent_rewrite(self):
        snapshot = inspect_document(b"Nome: Marcos", "txt")
        with self.assertRaisesRegex(DocumentEditError, "Nao foi encontrada"):
            await propose_document_edits(
                snapshot, "Troque o nome", AsyncMock(return_value={"edits": []})
            )

    def test_batches_never_silently_truncate(self):
        elements = [{"id": str(i), "text": "x" * 100} for i in range(20)]
        batches = element_batches(elements, max_chars=500)
        self.assertEqual(sum(len(batch) for batch in batches), 20)
        with self.assertRaises(DocumentEditError):
            element_batches(elements, max_chars=500, max_batches=1)


class DocumentToolSafetyTests(unittest.TestCase):
    def test_only_attached_accessible_files_can_be_edited(self):
        from neveai.tools.builtin import _attached_edit_source

        original = SimpleNamespace(user_id="me", id="file")
        with patch("neveai.models.files.Files.get_file_by_id", return_value=original):
            with self.assertRaises(DocumentEditError.__bases__[0]):
                _attached_edit_source("file", {"files": []}, {"id": "me"})
            with self.assertRaises(DocumentEditError.__bases__[0]):
                _attached_edit_source(
                    "file", {"files": [{"id": "file"}]}, {"id": "other"}
                )
            self.assertIs(
                _attached_edit_source(
                    "file", {"files": [{"id": "file"}]}, {"id": "me"}
                ),
                original,
            )

    def test_generation_limits_are_explicit_in_all_engines(self):
        from neveai.utils.generated_files import (
            _build_xlsx,
            _build_pptx,
            GeneratedFileError,
        )
        from neveai.utils.officecli_files import (
            _xlsx_commands,
            _pptx_commands,
            OfficeCLIError,
        )

        sheets = json.dumps(
            {"sheets": [{"name": str(i), "rows": []} for i in range(51)]}
        )
        slides = json.dumps(
            {"slides": [{"title": str(i), "content": []} for i in range(101)]}
        )
        for builder, content, error in [
            (_build_xlsx, sheets, GeneratedFileError),
            (_build_pptx, slides, GeneratedFileError),
            (_xlsx_commands, sheets, OfficeCLIError),
            (_pptx_commands, slides, OfficeCLIError),
        ]:
            with self.assertRaises(error):
                builder(content)

    def test_portuguese_local_edits_are_not_ignored_by_intent_gate(self):
        from neveai.utils.middleware import (
            _has_file_generation_intent,
            _build_file_generation_fallback_plan,
        )

        sources = [
            {
                "id": "file",
                "name": "Teste.docx",
                "content": "Nome: Marcos",
                "metadata": {},
            }
        ]
        for prompt in [
            "Troque Marcos por Mateus",
            "Substitua o nome por Ana",
            "Corrija a palavra errada",
        ]:
            self.assertTrue(_has_file_generation_intent(prompt, True))
            plan = _build_file_generation_fallback_plan(prompt, sources)
            self.assertEqual(plan["edit_mode"], "patch")
        self.assertEqual(
            _build_file_generation_fallback_plan(
                "Reescreva esse pdf e resuma ele", sources
            )["edit_mode"],
            "rebuild",
        )
        self.assertTrue(_has_file_generation_intent("Deixe o titulo em negrito", True))
        self.assertTrue(
            _has_file_generation_intent("Como deixar o titulo em negrito?", True)
        )


class DocumentPublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_derivative_keeps_original_and_records_diff(self):
        from neveai.tools.builtin import create_downloadable_file

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original.txt"
            path.write_bytes(b"Nome: Marcos\nManter\n")
            snapshot = inspect_document(path.read_bytes(), "txt")
            source = SimpleNamespace(
                id="source", filename="original.txt", path=str(path), user_id="me"
            )
            metadata = {"files": [{"id": "source"}]}
            published = {}

            def upload(**kwargs):
                published.update(
                    bytes=kwargs["file"].file.read(), metadata=kwargs["metadata"]
                )
                return SimpleNamespace(
                    id="derived",
                    meta={"name": "revisado.txt", "data": kwargs["metadata"]},
                )

            with (
                patch("neveai.models.files.Files.get_file_by_id", return_value=source),
                patch(
                    "neveai.tools.builtin.UserModel",
                    return_value=SimpleNamespace(id="me"),
                ),
                patch("neveai.routers.files.upload_file_handler", side_effect=upload),
            ):
                result = json.loads(
                    await create_downloadable_file(
                        "revisado.txt",
                        "",
                        "txt",
                        source_file_id="source",
                        edits=json.dumps(
                            [replacement(snapshot, "Nome: Marcos", "Nome: Mateus")]
                        ),
                        source_sha256=snapshot.digest,
                        __request__=SimpleNamespace(),
                        __user__={"id": "me"},
                        __metadata__=metadata,
                        __chat_id__="chat",
                        __message_id__="message",
                    )
                )
                self.assertEqual(result["status"], "success")
                self.assertEqual(published["bytes"], b"Nome: Mateus\nManter\n")
                self.assertEqual(path.read_bytes(), snapshot.data)
                self.assertEqual(
                    published["metadata"]["document_edit"]["source_file_id"], "source"
                )
                self.assertEqual(
                    metadata["pending_generated_files"][0]["id"], "derived"
                )
                stale = json.loads(
                    await create_downloadable_file(
                        "revisado.txt",
                        "",
                        "txt",
                        source_file_id="source",
                        edits="[]",
                        source_sha256="stale",
                        __request__=SimpleNamespace(),
                        __user__={"id": "me"},
                        __metadata__=metadata,
                        __chat_id__="chat",
                        __message_id__="message",
                    )
                )
                self.assertIn("mudou", stale["error"])
                self.assertEqual(len(metadata["pending_generated_files"]), 1)

    async def test_copy_keeps_exact_bytes(self):
        from neveai.tools.builtin import create_downloadable_file

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original.txt"
            path.write_bytes(b"\xef\xbb\xbfOriginal\r\n")
            source = SimpleNamespace(
                id="source", filename="original.txt", path=str(path), user_id="me"
            )
            captured = []

            def upload(**kwargs):
                captured.append(kwargs["file"].file.read())
                return SimpleNamespace(id="copy", meta={})

            with (
                patch("neveai.models.files.Files.get_file_by_id", return_value=source),
                patch(
                    "neveai.tools.builtin.UserModel",
                    return_value=SimpleNamespace(id="me"),
                ),
                patch("neveai.routers.files.upload_file_handler", side_effect=upload),
            ):
                result = json.loads(
                    await create_downloadable_file(
                        "copia.txt",
                        "",
                        "txt",
                        source_file_id="source",
                        edits="[]",
                        __request__=SimpleNamespace(),
                        __user__={"id": "me"},
                        __metadata__={"files": [{"id": "source"}]},
                        __chat_id__="chat",
                        __message_id__="message",
                    )
                )
                self.assertEqual(result["status"], "success")
                self.assertEqual(captured[0], path.read_bytes())


class DocumentValidationTests(unittest.TestCase):
    def test_generated_files_without_rag_content_can_be_edited_again(self):
        from neveai.utils.middleware import _get_file_generation_source_payloads

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original.txt"
            path.write_bytes(b"Nome: Marcos")
            file = SimpleNamespace(
                filename="original.txt", path=str(path), user_id="me", data={}, meta={}
            )
            with patch("neveai.models.files.Files.get_file_by_id", return_value=file):
                sources = _get_file_generation_source_payloads(
                    [{"id": "generated", "type": "file"}],
                    SimpleNamespace(role="user", id="me"),
                )
                self.assertEqual(sources[0]["content"], "Nome: Marcos")
                self.assertEqual(sources[0]["id"], "generated")
                self.assertEqual(
                    _get_file_generation_source_payloads(
                        [{"id": "generated", "type": "file"}],
                        SimpleNamespace(role="user", id="other"),
                    ),
                    [],
                )

    def test_rtf_unicode_and_structural_characters_round_trip(self):
        from neveai.utils.generated_files import build_generated_file
        from neveai.utils.document_validation import validate_document_output
        from neveai.utils.generated_files import read_rtf_text

        content = "Edi\u00e7\u00e3o de m\u00fasica: {Mateus} \\ arquivo\nNova linha\tColuna \U0001f600"
        _, data, _ = build_generated_file("document.rtf", content, "rtf")
        validate_document_output(data, "rtf", content)
        self.assertEqual(read_rtf_text(data.decode("ascii")), content)
        _, copy, _ = build_generated_file("document.rtf", data.decode("ascii"), "rtf")
        self.assertEqual(data, copy)

    def test_office_schema_checks_edited_docx_xlsx_pptx(self):
        from docx import Document
        from openpyxl import Workbook
        from pptx import Presentation
        from neveai.utils.document_validation import validate_document_output

        document = Document()
        document.add_paragraph("Marcos")
        workbook = Workbook()
        workbook.active.append(["Marcos"])
        presentation = Presentation()
        presentation.slides.add_slide(
            presentation.slide_layouts[5]
        ).shapes.title.text = "Marcos"
        for fmt, original in [
            ("docx", document),
            ("xlsx", workbook),
            ("pptx", presentation),
        ]:
            snapshot = inspect_document(saved(original), fmt)
            data, _ = apply_document_edits(
                snapshot, [replacement(snapshot, "Marcos", "Mateus")]
            )
            report = validate_document_output(data, fmt)
            self.assertEqual(report["validation"], "passed")
            self.assertIn("xml_structure", report["checks"])

    def test_office_envelope_success_does_not_hide_schema_errors(self):
        from docx import Document
        from neveai.utils.document_validation import validate_document_output

        with (
            patch(
                "neveai.utils.officecli_files._run_officecli",
                return_value={
                    "success": True,
                    "data": {"count": 1, "errors": ["invalid"]},
                },
            ),
            patch(
                "neveai.utils.officecli_files._officecli_binary",
                return_value=Path("fake"),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "schema"):
                validate_document_output(saved(Document()), "docx")

    def test_invalid_structured_outputs_are_rejected(self):
        from neveai.utils.document_validation import validate_document_output

        for fmt, data in [
            ("xml", b"<broken>"),
            ("json", b"{bad}"),
            ("yaml", b"[broken"),
            ("docx", b"not zip"),
            ("zip", b"not zip"),
        ]:
            with self.assertRaises(Exception):
                validate_document_output(data, fmt)

    def test_missing_slides_are_detected_from_actual_file(self):
        from neveai.utils.generated_files import _build_pptx
        from neveai.utils.document_validation import validate_document_output

        data = _build_pptx(json.dumps({"slides": [{"title": "One", "content": []}]}))
        with self.assertRaisesRegex(ValueError, "perdeu"):
            validate_document_output(data, "pptx", json.dumps({"slides": [{}, {}]}))

    def test_docx_context_preserves_paragraph_table_order(self):
        from docx import Document
        from neveai.utils.middleware import (
            _read_native_file_generation_content,
            _format_native_file_generation_source,
        )

        document = Document()
        document.add_paragraph("ANTES")
        document.add_table(rows=1, cols=1).cell(0, 0).text = "MEIO"
        document.add_paragraph("DEPOIS")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.docx"
            document.save(path)
            content = _format_native_file_generation_source(
                "source.docx",
                _read_native_file_generation_content(str(path), "fallback"),
            )
            self.assertLess(content.index("ANTES"), content.index("MEIO"))
            self.assertLess(content.index("MEIO"), content.index("DEPOIS"))

    def test_scanned_pdf_ocr_runs_only_on_missing_pages(self):
        from fpdf import FPDF
        from PIL import Image, ImageDraw, ImageFont
        from neveai.utils.pdf_document_text import read_pdf_document

        image = Image.new("RGB", (1000, 400), "white")
        draw = ImageDraw.Draw(image)
        font = (
            ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 42)
            if os.name == "nt"
            else ImageFont.load_default()
        )
        draw.text((30, 40), "Contrato de teste", fill="black", font=font)
        draw.text((30, 110), "Nome: Mateus", fill="black", font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        document = FPDF()
        document.add_page()
        document.set_font("Helvetica", size=12)
        document.text(20, 30, "Pagina com texto nativo")
        document.add_page()
        document.image(io.BytesIO(buffer.getvalue()), x=10, y=10, w=190)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scan.pdf"
            document.output(path)
            result = read_pdf_document(str(path))
            self.assertEqual(result["ocr_pages"], [2])
            self.assertIn("texto nativo", result["pages"][0]["text"])
            self.assertIn("Mateus", result["pages"][1]["text"])
            self.assertNotIn("ocr", result["pages"][0])
            self.assertGreater(result["pages"][1]["ocr_confidence"], 0.6)


@unittest.skipUnless(
    os.environ.get("NEVE_DOCUMENT_LLM_URL"), "Optional local LLM benchmark"
)
class ActualDocumentLLMTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_semantic_planner_routes_edit_and_summary_separately(self):
        import requests
        from neveai.utils import middleware

        async def generate(request, form_data, user):
            def complete():
                payload = {
                    **form_data,
                    "model": "local",
                    "chat_template_kwargs": {"enable_thinking": False},
                }
                response = requests.post(
                    os.environ["NEVE_DOCUMENT_LLM_URL"] + "/v1/chat/completions",
                    json=payload,
                    timeout=90,
                )
                response.raise_for_status()
                return response.json()

            return await asyncio.to_thread(complete)

        config = SimpleNamespace(TASK_MODEL="")
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(config=config))
        )
        source = {
            "id": "source",
            "name": "Teste.docx",
            "content": "Nome: Marcos",
            "metadata": {},
        }
        with (
            patch.object(
                middleware,
                "_get_file_generation_source_payloads",
                return_value=[source],
            ),
            patch.object(middleware, "generate_chat_completion", side_effect=generate),
            patch.object(middleware, "get_task_model_id", return_value="local"),
        ):
            for prompt, mode in [
                (
                    "Substitua somente Marcos por Mateus no documento. Mantenha todo o resto e a formatacao.",
                    "patch",
                ),
                ("Reescreva esse documento e resuma ele em um novo DOCX", "rebuild"),
            ]:
                plan = await middleware._plan_attachment_file_generation(
                    request,
                    {"model": "local"},
                    SimpleNamespace(),
                    {},
                    prompt,
                    [{"id": "source"}],
                    True,
                )
                self.assertEqual(plan["edit_mode"], mode)

    async def test_real_portuguese_edits_in_five_formats(self):
        import requests

        async def complete(messages, schema):
            def request():
                response = requests.post(
                    os.environ["NEVE_DOCUMENT_LLM_URL"] + "/v1/chat/completions",
                    json={
                        "model": "local",
                        "messages": messages,
                        "temperature": 0,
                        "max_tokens": 2048,
                        "chat_template_kwargs": {"enable_thinking": False},
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "document_edits",
                                "strict": True,
                                "schema": schema,
                            },
                        },
                    },
                    timeout=90,
                )
                response.raise_for_status()
                return json.loads(response.json()["choices"][0]["message"]["content"])

            return await asyncio.to_thread(request)

        from docx import Document
        from openpyxl import Workbook
        from pptx import Presentation

        document = Document()
        document.add_paragraph("Nome: Marcos")
        document.add_paragraph("Nao mudar o restante.")
        spreadsheet = Workbook()
        spreadsheet.active.append(["Nome", "Valor"])
        spreadsheet.active.append(["Marcos", 10])
        slides = Presentation()
        slides.slides.add_slide(slides.slide_layouts[5]).shapes.title.text = (
            "Nome: Marcos"
        )
        cases = [
            ("docx", saved(document)),
            ("xlsx", saved(spreadsheet)),
            ("pptx", saved(slides)),
            ("pdf", TextAndPdfEditsTests().pdf()),
            ("txt", b"Nome: Marcos\nNao mudar o restante.\n"),
        ]
        for fmt, data in cases:
            with self.subTest(format=fmt):
                snapshot = inspect_document(data, fmt)
                edits = await propose_document_edits(
                    snapshot,
                    "Substitua somente o nome Marcos por Ana. Mantenha todo o restante do documento, formatacao e imagens exatamente como estao.",
                    complete,
                )
                output, report = apply_document_edits(snapshot, edits)
                self.assertEqual(report["validation"], "passed")
                texts = [
                    item["text"] for item in inspect_document(output, fmt).elements
                ]
                self.assertTrue(any("Ana" in text for text in texts))
                self.assertFalse(any("Marcos" in text for text in texts))
                if fmt == "docx":
                    styled = await propose_document_edits(
                        snapshot,
                        "Coloque somente o paragrafo 'Nome: Marcos' em negrito e centralizado. Nao troque nenhuma palavra e mantenha o resto intacto.",
                        complete,
                    )
                    formatted, _ = apply_document_edits(snapshot, styled)
                    result = Document(io.BytesIO(formatted))
                    self.assertEqual(result.paragraphs[0].text, "Nome: Marcos")
                    self.assertTrue(result.paragraphs[0].runs[0].bold)
                    self.assertEqual(int(result.paragraphs[0].alignment), 1)
                    self.assertIsNone(result.paragraphs[1].runs[0].bold)
                    partial = await propose_document_edits(
                        snapshot,
                        "Deixe apenas a palavra Marcos em italico. Nao altere o texto nem a palavra Nome.",
                        complete,
                    )
                    partial_data, _ = apply_document_edits(snapshot, partial)
                    partial_result = Document(io.BytesIO(partial_data))
                    self.assertEqual(partial_result.paragraphs[0].text, "Nome: Marcos")
                    self.assertIsNone(partial_result.paragraphs[0].runs[0].italic)
                    self.assertTrue(partial_result.paragraphs[0].runs[-1].italic)


if __name__ == "__main__":
    unittest.main()
