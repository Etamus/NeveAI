import asyncio
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from neveai.utils import middleware
from neveai.utils.generated_files import build_generated_file
from neveai.utils.document_validation import validate_document_output


@unittest.skipUnless(
    os.environ.get("NEVE_DOCUMENT_LLM_URL")
    and os.environ.get("NEVE_DOCUMENT_STORY_FILE"),
    "Optional real-model story rewrite with an explicit source fixture",
)
class ActualStoryRewriteTests(unittest.IsolatedAsyncioTestCase):
    async def test_improve_story_prepares_an_edited_pdf_not_a_chat_response(self):
        import requests

        path = Path(os.environ["NEVE_DOCUMENT_STORY_FILE"])
        original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        text = await asyncio.to_thread(
            middleware._read_native_file_generation_content, str(path), ""
        )
        self.assertGreater(len(text), 1000)
        source = {
            "id": "source",
            "name": "Aquela que Permanece.pdf",
            "content": text,
            "metadata": {},
        }
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(config=SimpleNamespace(TASK_MODEL=""))
            )
        )
        prompt = os.environ.get("NEVE_DOCUMENT_STORY_PROMPT", "Melhore a historia")
        body = {
            "model": "local",
            "reasoning_mode": "quick",
            "no_think": True,
            "messages": [{"role": "user", "content": prompt}],
        }

        async def generate(request, form_data, user):
            def complete():
                payload = {
                    **form_data,
                    "model": "local",
                    "stream": False,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
                response = requests.post(
                    os.environ["NEVE_DOCUMENT_LLM_URL"] + "/v1/chat/completions",
                    json=payload,
                    timeout=300,
                )
                response.raise_for_status()
                return response.json()

            return await asyncio.to_thread(complete)

        async def emit(event):
            pass

        with (
            patch.object(
                middleware,
                "_get_file_generation_source_payloads",
                return_value=[source],
            ),
            patch.object(middleware, "get_task_model_id", return_value="local"),
            patch.object(middleware, "generate_chat_completion", side_effect=generate),
        ):
            plan = await middleware._plan_attachment_file_generation(
                request, body, SimpleNamespace(), {}, prompt, [{"id": "source"}], True
            )
            self.assertTrue(plan["should_generate_file"])
            self.assertEqual(plan["output_format"], "pdf")
            self.assertEqual(plan["edit_mode"], "rebuild")
            content = ""
            issues = None
            for attempt in range(2):
                content, reasoning, _, sources = (
                    await middleware._generate_attachment_deliverable_adaptive(
                        request,
                        body,
                        SimpleNamespace(),
                        {},
                        "pdf",
                        emit,
                        plan,
                        repair_issues=issues,
                        previous_content=content,
                    )
                )
                issues = middleware._get_file_generation_coverage_issues(
                    plan["source_payloads"], content, sources, "pdf", plan, reasoning
                )
                if not issues:
                    issues = await middleware._review_generated_file_content(
                        request, body, SimpleNamespace(), {}, "pdf", plan, content
                    )
                if not issues:
                    break
                print(f"Fidelity repair {attempt + 1}: {issues}")
            self.assertFalse(issues, issues)

        self.assertNotEqual(content.strip(), text.strip())
        for name in ("Kael", "Lysa"):
            self.assertIn(name, content)
        if "resum" in prompt.casefold():
            self.assertLess(len(content.split()), len(text.split()) * 0.6)
            self.assertGreater(len(content), 300)
        else:
            self.assertGreater(len(content), len(text) / 2)
        _, data, _ = build_generated_file("Historia-melhorada.pdf", content, "pdf")
        validation = await asyncio.to_thread(
            validate_document_output, data, "pdf", content
        )
        self.assertEqual(validation["validation"], "passed")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), original_hash)
        output = Path(
            os.environ.get(
                "NEVE_DOCUMENT_STORY_OUTPUT",
                "logs/ferramentas-validacao/Historia-melhorada.pdf",
            )
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        print(
            f"Validated rewritten PDF: {output}; source={len(text)} chars, output={len(content)} chars"
        )


if __name__ == "__main__":
    unittest.main()
