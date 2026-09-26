import unittest

from neveai.routers.stable_diffusion import (
    QWEN_IMAGE_21_CFG_SCALE,
    QWEN_IMAGE_21_STEPS,
    _normalize_qwen_reference_tokens,
)


class QwenImageReferencePromptTests(unittest.TestCase):
    def test_uses_stable_diffusion_cpp_recommended_qwen_cfg(self):
        self.assertEqual(QWEN_IMAGE_21_CFG_SCALE, 6.0)

    def test_quality_mode_uses_validated_step_count(self):
        self.assertEqual(QWEN_IMAGE_21_STEPS, 30)

    def test_normalizes_portuguese_reference_groups_without_translating_prompt(self):
        prompt = "Faça os personagens das imagens 1 e 2 em uma mesa; use a imagem 3 como estilo."

        result = _normalize_qwen_reference_tokens(prompt, 3)

        self.assertIn("Faça os personagens das <image1> e <image2>", result)
        self.assertIn("use a <image3> como estilo", result)
        self.assertNotIn("Reference images in attachment order", result)

    def test_preserves_existing_tokens_and_lists_unmentioned_references(self):
        prompt = "Keep the subject from <image1> and use image 2 for lighting."

        result = _normalize_qwen_reference_tokens(prompt, 3)

        self.assertEqual(result.count("<image1>"), 1)
        self.assertIn("use <image2> for lighting", result)
        self.assertTrue(result.startswith("Reference images in attachment order: <image3>."))

    def test_does_not_rewrite_numbers_outside_available_references(self):
        prompt = "Use imagem 4 e preserve 2 personagens."

        result = _normalize_qwen_reference_tokens(prompt, 2)

        self.assertIn("4", result)
        self.assertIn("2 personagens", result)


if __name__ == "__main__":
    unittest.main()
