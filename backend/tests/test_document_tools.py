import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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

    def test_document_question_in_tools_mode_produces_a_report(self):
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

        self.assertEqual(plan["operation"], "create")
        self.assertEqual(plan["output_format"], "docx")
        self.assertFalse(plan["preserve_all_unique_content"])

    def test_tools_mode_does_not_ignore_plain_questions(self):
        self.assertTrue(
            middleware._has_file_generation_intent(
                "Qual e a capital de Minas Gerais?", False
            )
        )

    def test_tools_mode_does_not_ignore_instructional_questions(self):
        self.assertTrue(
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

    def test_tools_mode_does_not_ignore_attachment_questions(self):
        self.assertTrue(
            middleware._has_file_generation_intent(
                "Qual e a data citada neste PDF?", True
            )
        )

    def test_improvement_and_short_followups_always_have_a_fallback(self):
        source = {
            "id": "source",
            "name": "Historia.pdf",
            "content": "Historia completa",
        }
        for prompt in [
            "Melhore a historia",
            "Aprimore o texto",
            "Improve the story",
            "Continue",
            "Faca outra",
            "Sim",
            "Bom dia",
            "Qual e a data?",
        ]:
            for sources in ([], [source]):
                with self.subTest(prompt=prompt, attached=bool(sources)):
                    self.assertTrue(
                        middleware._has_file_generation_intent(prompt, bool(sources))
                    )
                    plan = middleware._build_file_generation_fallback_plan(
                        prompt, sources
                    )
                    self.assertTrue(plan["should_generate_file"])
                    self.assertEqual(plan["objective"], prompt)
                    self.assertTrue(plan["requires_semantic_rewrite"])
        plan = middleware._build_file_generation_fallback_plan(
            "Melhore a historia", [source]
        )
        self.assertEqual(plan["output_format"], "pdf")
        self.assertEqual(plan["edit_mode"], "rebuild")
        self.assertIn("rewrite", plan["semantic_transformations"])

    def test_empty_request_does_not_generate_a_document(self):
        self.assertFalse(middleware._has_file_generation_intent("  ", True))
        self.assertIsNone(middleware._build_file_generation_fallback_plan("  ", []))


class RequiredDocumentPlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_declared_semantic_actions_cannot_be_erased_by_a_second_classifier(
        self,
    ):
        import json

        source = {
            "id": "source",
            "name": "Historia.pdf",
            "content": "Historia completa",
            "metadata": {},
        }
        for action, prompt in [
            ("rewrite", "Melhore a historia"),
            ("translate", "Traduza o PDF para ingles"),
            ("select", "Extraia somente os eventos principais"),
        ]:
            with self.subTest(action=action):
                model_plan = {
                    "should_generate_file": True,
                    "operation": "convert",
                    "edit_mode": "rebuild",
                    "output_format": "pdf",
                    "semantic_transformations": [action],
                    "requires_semantic_rewrite": False,
                    "preserve_all_unique_content": True,
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(model_plan)}}]
                }
                with (
                    patch.object(
                        middleware,
                        "_get_file_generation_source_payloads",
                        return_value=[source],
                    ),
                    patch.object(middleware, "get_task_model_id", return_value="local"),
                    patch.object(
                        middleware,
                        "generate_chat_completion",
                        AsyncMock(return_value=response),
                    ),
                    patch.object(
                        middleware,
                        "_verify_single_source_semantic_rewrite",
                        AsyncMock(return_value=False),
                    ) as verify,
                ):
                    plan = await self.plan(prompt, [{"id": "source"}])
                verify.assert_not_awaited()
                self.assertTrue(plan["requires_semantic_rewrite"])
                self.assertIn(action, plan["semantic_transformations"])
                self.assertIsNone(
                    middleware._get_structural_file_generation_result(plan, "pdf")
                )
                if action == "select":
                    self.assertFalse(plan["preserve_all_unique_content"])

    def test_partial_summary_does_not_require_shortening_unaffected_sections(self):
        text = " ".join(f"evento{i}" for i in range(300))
        plan = {
            "objective": "Resuma apenas o primeiro paragrafo e mantenha o resto",
            "semantic_transformations": ["summarize"],
            "preserve_all_unique_content": False,
        }
        self.assertFalse(
            middleware._get_file_generation_coverage_issues(
                [{"name": "source.txt", "content": text}],
                text,
                ["source.txt"],
                "pdf",
                plan,
            )
        )

    def test_summary_guard_distinguishes_instructions_from_quoted_document_data(self):
        for prompt in [
            "Resuma o conteudo do pdf",
            "Quero um resumo do documento",
            "Summarize the document",
            "Resumo do PDF",
        ]:
            with self.subTest(prompt=prompt):
                self.assertTrue(middleware._requests_document_summary(prompt))
        for prompt in [
            'Troque "Resumo" por "Introducao"',
            'Remova o titulo "Resumo"',
            "Nao resuma o documento",
            "Nao quero um resumo",
            "Do not summarize the document",
        ]:
            with self.subTest(prompt=prompt):
                self.assertFalse(middleware._requests_document_summary(prompt))

    async def test_summary_cannot_be_downgraded_to_lossless_conversion(self):
        import json

        source = {
            "id": "source",
            "name": "Historia.pdf",
            "content": "Historia completa",
            "metadata": {},
        }
        wrong_plan = {
            "should_generate_file": True,
            "operation": "convert",
            "edit_mode": "rebuild",
            "output_format": "pdf",
            "semantic_transformations": [],
            "requires_semantic_rewrite": False,
            "preserve_all_unique_content": True,
        }
        response = {"choices": [{"message": {"content": json.dumps(wrong_plan)}}]}
        with (
            patch.object(
                middleware,
                "_get_file_generation_source_payloads",
                return_value=[source],
            ),
            patch.object(middleware, "get_task_model_id", return_value="local"),
            patch.object(
                middleware, "generate_chat_completion", AsyncMock(return_value=response)
            ),
            patch.object(
                middleware,
                "_verify_single_source_semantic_rewrite",
                AsyncMock(return_value=False),
            ) as verify,
        ):
            plan = await self.plan("Resuma o conteudo do pdf", [{"id": "source"}])
        verify.assert_not_awaited()
        self.assertTrue(plan["requires_semantic_rewrite"])
        self.assertIn("summarize", plan["semantic_transformations"])
        self.assertFalse(plan["preserve_all_unique_content"])
        self.assertIsNone(
            middleware._get_structural_file_generation_result(plan, "pdf")
        )

    def test_semantic_actions_block_structural_copy_even_with_conflicting_flags(self):
        for action in ["summarize", "translate", "rewrite", "select", "merge"]:
            with self.subTest(action=action):
                self.assertIsNone(
                    middleware._get_structural_file_generation_result(
                        {
                            "requires_semantic_rewrite": False,
                            "semantic_transformations": [action],
                            "operation": "convert",
                            "source_payloads": [
                                {"name": "source.txt", "content": "Source"}
                            ],
                        },
                        "txt",
                    )
                )

    def test_summary_near_original_length_is_rejected_without_truncating_it(self):
        text = " ".join(f"evento{i}" for i in range(300))
        source = {"name": "source.txt", "content": text}
        plan = {
            "semantic_transformations": ["summarize"],
            "preserve_all_unique_content": False,
        }
        issues = middleware._get_file_generation_coverage_issues(
            [source], text, ["source.txt"], "pdf", plan
        )
        self.assertTrue(any("resumo" in issue for issue in issues))
        self.assertFalse(
            middleware._get_file_generation_coverage_issues(
                [source], "Resumo dos fatos essenciais.", ["source.txt"], "pdf", plan
            )
        )

    async def test_selective_operations_still_receive_an_objective_audit(self):
        import json

        response = {
            "choices": [{"message": {"content": json.dumps({"approved": True})}}]
        }
        with (
            patch.object(middleware, "get_task_model_id", return_value="local"),
            patch.object(
                middleware, "generate_chat_completion", AsyncMock(return_value=response)
            ) as generate,
        ):
            issues = await middleware._review_generated_file_content(
                SimpleNamespace(
                    app=SimpleNamespace(
                        state=SimpleNamespace(config=SimpleNamespace(TASK_MODEL=""))
                    )
                ),
                {"model": "local"},
                SimpleNamespace(),
                {},
                "pdf",
                {
                    "preserve_all_unique_content": False,
                    "objective": "Resuma",
                    "source_payloads": [{"name": "source.txt", "content": "Source"}],
                },
                "Resumo",
            )
        self.assertFalse(issues)
        generate.assert_awaited_once()
        system = generate.call_args.kwargs["form_data"]["messages"][0]["content"]
        self.assertIn("omitting details is expected", system)

    async def plan(self, prompt, files, enabled=True):
        return await middleware._plan_attachment_file_generation(
            SimpleNamespace(
                app=SimpleNamespace(
                    state=SimpleNamespace(config=SimpleNamespace(TASK_MODEL=""))
                )
            ),
            {"model": "local", "messages": [{"role": "user", "content": prompt}]},
            SimpleNamespace(),
            {},
            prompt,
            files,
            enabled,
        )

    async def test_negative_or_failed_planner_cannot_disable_tools_mode(self):
        source = {
            "id": "source",
            "name": "Historia.pdf",
            "content": "Historia completa",
            "metadata": {},
        }
        for response in (
            {"choices": [{"message": {"content": '{"should_generate_file":false}'}}]},
            RuntimeError("planner unavailable"),
        ):
            with self.subTest(response=str(response)):
                generate = (
                    AsyncMock(side_effect=response)
                    if isinstance(response, Exception)
                    else AsyncMock(return_value=response)
                )
                with (
                    patch.object(
                        middleware,
                        "_get_file_generation_source_payloads",
                        return_value=[source],
                    ),
                    patch.object(middleware, "get_task_model_id", return_value="local"),
                    patch.object(middleware, "generate_chat_completion", generate),
                ):
                    plan = await self.plan("Melhore a historia", [{"id": "source"}])
                self.assertTrue(plan["should_generate_file"])
                self.assertEqual(plan["edit_mode"], "rebuild")
                self.assertEqual(plan["output_format"], "pdf")

    async def test_unreadable_attachments_fail_instead_of_becoming_plain_chat(self):
        with (
            patch.object(
                middleware, "_get_file_generation_source_payloads", return_value=[]
            ),
            patch.object(
                middleware, "generate_chat_completion", AsyncMock()
            ) as generate,
        ):
            with self.assertRaisesRegex(ValueError, "ler os anexos"):
                await self.plan("Melhore a historia", [{"id": "source"}])
            generate.assert_not_awaited()

    async def test_disabled_mode_does_not_run_the_document_pipeline(self):
        with (
            patch.object(middleware, "_get_file_generation_source_payloads") as read,
            patch.object(
                middleware, "generate_chat_completion", AsyncMock()
            ) as generate,
        ):
            self.assertIsNone(await self.plan("Melhore a historia", [], enabled=False))
            read.assert_not_called()
            generate.assert_not_awaited()

    async def test_cancellation_does_not_start_another_generation(self):
        with (
            patch.object(
                middleware, "_get_file_generation_source_payloads", return_value=[]
            ),
            patch.object(middleware, "get_task_model_id", return_value="local"),
            patch.object(
                middleware,
                "generate_chat_completion",
                AsyncMock(side_effect=asyncio.CancelledError()),
            ) as generate,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await self.plan("Melhore a historia", [])
            self.assertEqual(generate.await_count, 1)


if __name__ == "__main__":
    unittest.main()
