import base64
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx

from neveai.routers.image_quality_generation import NeveImage21Runtime, PE_EDIT_SCOPE, PE_SYSTEM_FILE


def response(content, status=200):
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]},
                          request=httpx.Request("POST", "http://127.0.0.1/v1/chat/completions"))


class ImagePromptFidelityTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, reply, images=None, cpu=False, prompt=None):
        runtime = NeveImage21Runtime()
        runtime._cpu_mode = cpu
        runtime._start, runtime._stop = AsyncMock(return_value="http://127.0.0.1"), AsyncMock()
        client = AsyncMock()
        client.post.return_value = reply
        factory = Mock()
        factory.return_value.__aenter__ = AsyncMock(return_value=client)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        self.runtime, self.client = runtime, client
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            system_file = folder / PE_SYSTEM_FILE
            system_file.write_text("Original native editing instructions.", encoding="utf-8")
            with patch("neveai.routers.llamacpp.LLAMACPP_SERVER_BIN", Path(__file__)), \
                    patch.object(runtime, "_pe_directory", return_value=folder), \
                    patch.object(runtime, "_pe_file", return_value="test-heretic.gguf"), \
                    patch("neveai.routers.image_quality_generation.httpx.AsyncClient", factory):
                result = await runtime._plan_edit(prompt or 'Replace the person using image 2. Remove the arm. Write "Keep 42".',
                                                  images or [b"canvas", b"identity"], AsyncMock())
            self.assertEqual(system_file.read_text(encoding="utf-8"), "Original native editing instructions.")
            return result

    async def test_native_single_request_keeps_model_original_system_and_reference_order(self):
        expected = "Replace the requested subject; preserve only the specified pose."
        for count in (1, 4, 10):
            images = [f"image-{index}".encode() for index in range(count)]
            result = await self.exercise(response(json.dumps({"rewritten_prompt": expected})), images)
            self.assertEqual(result, expected)
            self.client.post.assert_awaited_once()
            request = self.client.post.await_args.kwargs["json"]
            self.assertEqual(request["model"], "test-heretic.gguf")
            self.assertEqual(request["messages"][0]["content"], "Original native editing instructions." + PE_EDIT_SCOPE)
            self.assertEqual(len(request["messages"]), 2)
            self.assertNotIn("response_format", request)
            self.assertEqual(request["temperature"], 0.2)
            parts = request["messages"][1]["content"]
            self.assertIn('"Keep 42"', parts[-1]["text"])
            self.assertIn("Remove the arm", parts[-1]["text"])
            self.assertEqual([base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
                              for part in parts[:-1]], images)
            self.runtime._stop.assert_awaited_once()

    async def test_invalid_native_plan_still_fails_and_cleans_up_worker(self):
        with self.assertRaises(RuntimeError):
            await self.exercise(response("No JSON directive"))
        self.client.post.assert_awaited_once()
        self.runtime._stop.assert_awaited_once()

    async def test_failed_request_has_no_new_retry_or_secondary_auditor(self):
        with self.assertRaises(httpx.HTTPStatusError):
            await self.exercise(response("", 500))
        self.client.post.assert_awaited_once()
        self.runtime._stop.assert_awaited_once()

    async def test_cpu_keeps_native_planner_loading_and_single_call(self):
        await self.exercise(response('{"rewritten_prompt":"Edit only the requested text."}'), cpu=True)
        command = self.runtime._start.await_args.args[0]
        self.assertIn("--no-mmproj-offload", command)
        self.assertEqual(command[command.index("--n-gpu-layers") + 1], "0")
        self.client.post.assert_awaited_once()

    def test_scope_rules_are_general_and_preserve_narrow_and_broad_edits(self):
        self.assertIn("face-only edit must preserve the body", PE_EDIT_SCOPE)
        self.assertIn("explicitly broad changes or new compositions", PE_EDIT_SCOPE)
        self.assertIn("Do not weaken, exaggerate or censor", PE_EDIT_SCOPE)
        for case_specific_word in ("robot", "tentacle", "medieval", "dungeon", "calabolso"):
            self.assertNotIn(case_specific_word, PE_EDIT_SCOPE.lower())

    def test_background_policy_distinguishes_replacement_from_partial_edits(self):
        self.assertIn("scene-defining fixtures must be absent", PE_EDIT_SCOPE)
        self.assertIn("unless the user explicitly requests them", PE_EDIT_SCOPE)
        self.assertIn("style-only, texture-only, lighting-only or localized edit", PE_EDIT_SCOPE)
        self.assertIn("instead of confidently translating it into a different place", PE_EDIT_SCOPE)
        self.assertIn("Do not list the old background's objects", PE_EDIT_SCOPE)
        self.assertIn("does not remove user-requested details, literal text or exclusions", PE_EDIT_SCOPE)

    async def test_generation_details_are_copied_atomically_without_cross_request_leaks(self):
        runtime = NeveImage21Runtime()
        async def recover(prompt, *args):
            runtime._generation_details = {"effective_prompt": prompt, "seed": "42"}
            await asyncio.sleep(0)
            return "result-" + prompt
        first, second = {}, {}
        with patch.object(runtime, "_run_recovery", side_effect=recover):
            results = await asyncio.gather(
                runtime.run("first", "auto", [], None, AsyncMock(), details=first),
                runtime.run("second", "auto", [], None, AsyncMock(), details=second))
        self.assertEqual(results, ["result-first", "result-second"])
        self.assertEqual(first["effective_prompt"], "first")
        self.assertEqual(second["effective_prompt"], "second")

    async def test_failed_generation_never_publishes_stale_generation_details(self):
        runtime = NeveImage21Runtime()
        runtime._generation_details = {"effective_prompt": "previous request"}
        details = {}
        with patch.object(runtime, "_run_recovery", AsyncMock(side_effect=RuntimeError("failed"))):
            with self.assertRaises(RuntimeError):
                await runtime.run("new request", "auto", [], None, AsyncMock(), details=details)
        self.assertEqual(details, {})
        self.assertEqual(runtime._generation_details, {})

    async def test_native_planner_keeps_multiline_operations_and_literal_text(self):
        prompt = 'Use imagem 1.\nRemove only the arm.\nWrite "Line  one\nLine two" exactly.'
        await self.exercise(response('{"rewritten_prompt":"Edit the requested targets."}'), images=[b"canvas"], prompt=prompt)
        text = self.client.post.await_args.kwargs["json"]["messages"][1]["content"][-1]["text"]
        self.assertEqual(text, prompt.replace("imagem 1", "<image1>"))

    async def test_background_scope_preserves_explicit_user_constraints_and_reference_roles(self):
        prompts = (
            "Replace the whole background using image 3. Keep only the subject and pose of image 1.",
            "Change only the floor texture using image 3; preserve the room and its red lighting.",
            "Match only the rendering style of image 2; do not import its scenery or lighting.",
            "Replace the room but explicitly preserve its red lighting and the subject's pose.",
            "Replace only the view through the window; keep the interior unchanged.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                await self.exercise(response('{"rewritten_prompt":"Execute the requested edit."}'),
                                    images=[b"canvas", b"style", b"texture"], prompt=prompt)
                request = self.client.post.await_args.kwargs["json"]
                text = request["messages"][1]["content"][-1]["text"]
                expected = prompt
                for index in (1, 2, 3):
                    expected = expected.replace(f"image {index}", f"<image{index}>")
                self.assertTrue(text.endswith(expected))
                self.assertTrue(text.startswith("Reference images in attachment order:"))
                self.client.post.assert_awaited_once()
