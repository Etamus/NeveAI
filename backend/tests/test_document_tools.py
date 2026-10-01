import unittest

from neveai.utils import middleware


class DocumentToolConfigurationTests(unittest.TestCase):
    def test_runtime_limits_used_by_document_pipeline_are_defined(self):
        self.assertGreater(middleware.FILE_DIRECT_CONTEXT_MAX_CHARS, 0)
        self.assertGreater(middleware.FILE_RETRIEVAL_FALLBACK_MAX_CHARS, 0)
        self.assertGreater(middleware.FILE_RETRIEVAL_FALLBACK_CHUNK_CHARS, 0)
        self.assertGreater(middleware.FILE_QUERY_GENERATION_TIMEOUT_SECONDS, 0)
        self.assertGreater(middleware.FILE_RETRIEVAL_TIMEOUT_SECONDS, 0)

    def test_supported_document_formats_have_generation_guidance(self):
        self.assertIn("pdf", middleware.FILE_GENERATION_OUTPUT_FORMATS)
        self.assertIn("docx", middleware.FILE_GENERATION_OUTPUT_FORMATS)
        self.assertIn("xlsx", middleware.FILE_GENERATION_OUTPUT_FORMATS)
        self.assertIn("pptx", middleware.FILE_GENERATION_OUTPUT_FORMATS)
        self.assertIn("pdf", middleware.FILE_GENERATION_FORMAT_GUIDANCE)

    def test_pdf_rewrite_and_summary_has_a_deterministic_fallback(self):
        sources = [
            {
                "id": "source-1",
                "name": "Aquela que Permanece.pdf",
                "content": "Conteudo do documento",
                "metadata": {},
            }
        ]

        plan = middleware._build_file_generation_fallback_plan(
            "Reescreva esse pdf e resuma ele", sources
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan["output_format"], "pdf")
        self.assertEqual(plan["operation"], "edit")
        self.assertIn("rewrite", plan["semantic_transformations"])
        self.assertIn("summarize", plan["semantic_transformations"])
        self.assertFalse(plan["preserve_all_unique_content"])

    def test_document_question_does_not_force_a_download(self):
        sources = [
            {
                "id": "source-1",
                "name": "Manual.pdf",
                "content": "Conteudo do documento",
                "metadata": {},
            }
        ]

        plan = middleware._build_file_generation_fallback_plan(
            "Qual e a data citada neste PDF?", sources
        )

        self.assertIsNone(plan)

    def test_plain_chat_skips_file_generation_planner(self):
        self.assertFalse(
            middleware._has_file_generation_intent(
                "Qual e a capital de Minas Gerais?", False
            )
        )

    def test_instructional_file_question_skips_file_generation_planner(self):
        self.assertFalse(
            middleware._has_file_generation_intent(
                "Como criar um PDF bem formatado?", False
            )
        )

    def test_explicit_deliverable_uses_file_generation_planner(self):
        self.assertTrue(
            middleware._has_file_generation_intent(
                "Crie um PDF com um resumo desta conversa", False
            )
        )

    def test_attachment_rewrite_uses_file_generation_planner(self):
        self.assertTrue(
            middleware._has_file_generation_intent(
                "Reescreva esse documento e resuma ele", True
            )
        )

    def test_attachment_question_skips_file_generation_planner(self):
        self.assertFalse(
            middleware._has_file_generation_intent(
                "Qual e a data citada neste PDF?", True
            )
        )


if __name__ == "__main__":
    unittest.main()
