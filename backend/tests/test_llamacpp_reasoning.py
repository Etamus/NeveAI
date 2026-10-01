import unittest

from neveai.routers.llamacpp import (
    _detect_reasoning_control,
    _resolve_reasoning_settings,
)


class LlamaCppReasoningModeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
