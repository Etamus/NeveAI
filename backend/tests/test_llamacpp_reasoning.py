import unittest
from unittest.mock import AsyncMock, Mock, patch

from neveai.routers.llamacpp import (
    _detect_reasoning_control,
    _resolve_reasoning_settings,
    _kill_orphan_llama_servers,
    LLAMACPP_SERVER_DIR,
    LocalModelManager,
)


class LlamaCppReasoningModeTests(unittest.TestCase):
    def test_neve_sense_uses_effort_even_without_runtime_properties(self):
        for filename in ("Neve-Sense-2-20B-Q4.gguf", "Neve-Sense2-20B.gguf"):
            self.assertEqual(_detect_reasoning_control(filename), "effort")

    def test_effort_slider_levels(self):
        for mode, extended, unlimited, effort in (
            ("quick", False, False, "low"),
            ("reasoning", False, False, "medium"),
            ("reasoning", True, False, "high"),
            ("reasoning", True, True, "high"),
        ):
            with self.subTest(effort=effort, unlimited=unlimited):
                self.assertEqual(
                    _resolve_reasoning_settings("effort", mode, extended, unlimited),
                    (False, None, effort),
                )

    def test_maximum_reasoning_has_no_fixed_budget(self):
        for control in ("toggle", "budget", "unknown"):
            self.assertEqual(
                _resolve_reasoning_settings(control, "reasoning", True, True),
                (False, None, None),
            )
        self.assertEqual(
            _resolve_reasoning_settings("effort", "reasoning", True, True),
            (False, None, "high"),
        )

    def test_quick_remains_quick_even_with_stale_unlimited_flag(self):
        self.assertEqual(
            _resolve_reasoning_settings("toggle", "quick", True, True),
            (True, None, None),
        )

    def test_cleanup_preserves_live_sessions_and_external_servers(self):
        owned = Mock(pid=100, info={"name": "llama-server.exe", "ppid": 200, "cmdline": [str(LLAMACPP_SERVER_DIR / "llama-server.exe")]})
        external = Mock(pid=101, info={"name": "llama-server.exe", "ppid": 0, "cmdline": ["C:/Other/llama-server.exe"]})
        with patch("psutil.process_iter", return_value=[owned, external]), patch("psutil.pid_exists", return_value=True):
            _kill_orphan_llama_servers()
        owned.kill.assert_not_called()
        external.kill.assert_not_called()

    def test_cleanup_only_removes_owned_server_with_dead_parent(self):
        owned = Mock(pid=100, info={"name": "llama-server.exe", "ppid": 200, "cmdline": [str(LLAMACPP_SERVER_DIR / "llama-server.exe")]})
        with patch("psutil.process_iter", return_value=[owned]), patch("psutil.pid_exists", return_value=False):
            _kill_orphan_llama_servers()
        owned.kill.assert_called_once()

    def test_qwen_quick_mode_disables_thinking(self):
        control = _detect_reasoning_control(
            "Qwen3.5-9B.gguf",
            {"tokenizer.chat_template": "{% if enable_thinking %}"},
        )

        self.assertEqual(control, "toggle")
        self.assertEqual(
            _resolve_reasoning_settings(control, "quick", False),
            (True, None, None),
        )

    def test_budget_model_quick_mode_disables_thinking(self):
        control = _detect_reasoning_control(
            "reasoning-model.gguf",
            {"tokenizer.chat_template": "{{ thinking_budget }}"},
        )

        self.assertEqual(control, "budget")
        self.assertEqual(
            _resolve_reasoning_settings(control, "quick", False),
            (True, None, None),
        )

    def test_unknown_model_quick_mode_uses_no_think_fallback(self):
        self.assertEqual(
            _resolve_reasoning_settings("unknown", "quick", None),
            (True, None, None),
        )

    def test_gpt_oss_quick_mode_uses_low_effort(self):
        control = _detect_reasoning_control("GPT-OSS-20B.gguf")

        self.assertEqual(control, "effort")
        self.assertEqual(
            _resolve_reasoning_settings(control, "quick", False),
            (False, None, "low"),
        )

    def test_reasoning_mode_preserves_regular_and_extended_budgets(self):
        self.assertEqual(
            _resolve_reasoning_settings("toggle", "reasoning", False),
            (False, 512, None),
        )
        self.assertEqual(
            _resolve_reasoning_settings("toggle", "reasoning", True),
            (False, 4096, None),
        )


class ReasoningPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_level_reaches_llama_server_with_the_correct_budget(self):
        manager = LocalModelManager.__new__(LocalModelManager)
        manager._loaded = {"test": Mock(mmproj_filename=None)}
        manager._ports = {"test": 9999}
        response = Mock(status_code=200)
        response.json.return_value = {"choices": []}
        client = Mock(get=AsyncMock(return_value=response), post=AsyncMock(return_value=response))
        for mode, extended, unlimited, budget in (
            ("quick", False, False, None),
            ("reasoning", False, False, 512),
            ("reasoning", True, False, 4096),
            ("reasoning", True, True, None),
        ):
            no_think, actual_budget, effort = _resolve_reasoning_settings("toggle", mode, extended, unlimited)
            with patch.object(manager, "is_model_loaded", return_value=True), patch("neveai.routers.llamacpp._get_http_client", return_value=client):
                await manager.chat_completion("test", [{"role": "user", "content": "Teste"}], no_think=no_think, thinking_budget_tokens=actual_budget, reasoning_effort=effort)
            payload = client.post.call_args.kwargs["json"]
            self.assertEqual(payload.get("thinking_budget_tokens"), budget)
            if budget is None:
                self.assertNotIn("thinking_budget_tokens", payload)
            self.assertEqual(payload["max_tokens"], -1)
            if mode == "quick":
                self.assertEqual(payload["chat_template_kwargs"]["enable_thinking"], False)


if __name__ == "__main__":
    unittest.main()
