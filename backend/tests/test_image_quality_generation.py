import unittest
from unittest.mock import patch

from neveai.routers.image_quality_generation import (
    ENCODER_FILE,
    MODEL_FILE,
    PE_FILE,
    PE_LOW_VRAM_FILE,
    PE_REPO,
    PE_THINKING_TOKENS,
    PE_VISION_FILE,
    STEPS,
    NeveImage21Runtime,
    _extract_pe_prompt,
    _fit_reference,
    _pe_file_for_hardware,
)
from neveai.routers.stable_diffusion import (
    QWEN_IMAGE_21_OFFICIAL_QUALITY,
    normalize_image_quality,
)


class NeveImage21ComfyTests(unittest.TestCase):
    def test_reference_canvas_preserves_aspect_and_aligns_to_32(self):
        width, height = _fit_reference(1063, 1480)
        self.assertEqual((width, height), (992, 1344))
        self.assertEqual(width % 32, 0)
        self.assertEqual(height % 32, 0)

    def test_edit_workflow_uses_native_images_and_requested_sampler(self):
        graph = NeveImage21Runtime.build_workflow(
            "Troque o personagem da imagem 1 pelo da imagem 2", 992, 1344,
            ["card.png", "portrait.png"], 42,
        )
        self.assertEqual(graph["1"]["inputs"]["unet_name"], MODEL_FILE)
        self.assertEqual(graph["2"]["inputs"]["clip_name"], ENCODER_FILE)
        self.assertIn("<image1>", graph["4"]["inputs"]["prompt"])
        self.assertIn("<image2>", graph["4"]["inputs"]["prompt"])
        self.assertEqual(graph["4"]["inputs"]["resolution"], 0)
        self.assertEqual(graph["4"]["inputs"]["images.image_1"], ["9", 0])
        self.assertEqual(graph["4"]["inputs"]["images.image_2"], ["10", 0])
        self.assertEqual(graph["5"]["inputs"]["latent_image"], ["4", 2])
        self.assertEqual(graph["5"]["inputs"]["steps"], 40)
        self.assertEqual(graph["5"]["inputs"]["cfg"], 1.0)
        self.assertEqual(graph["5"]["inputs"]["sampler_name"], "euler")
        self.assertEqual(graph["5"]["inputs"]["scheduler"], "simple")
        self.assertLessEqual(PE_THINKING_TOKENS, 800)

    def test_text_to_image_uses_selected_canvas_without_pe(self):
        graph = NeveImage21Runtime.build_workflow("Uma flor", 1216, 704, [], 42)
        self.assertEqual(graph["5"]["inputs"]["latent_image"], ["6", 0])
        self.assertEqual((graph["6"]["inputs"]["width"], graph["6"]["inputs"]["height"]), (1216, 704))
        self.assertNotIn("9", graph)

    def test_pe_output_and_fast_mode_migration_are_independent(self):
        content = '<think>plan</think> {"rewritten_prompt":"Edit <image1> using <image2>","ratio_follow":"<image1>"}'
        self.assertEqual(_extract_pe_prompt(content), "Edit <image1> using <image2>")
        self.assertEqual(normalize_image_quality(QWEN_IMAGE_21_OFFICIAL_QUALITY), QWEN_IMAGE_21_OFFICIAL_QUALITY)
        self.assertEqual(normalize_image_quality("qwen_image_2_1"), "qwen_image_2s")
        self.assertEqual(STEPS, 40)
        self.assertEqual(ENCODER_FILE, "qwen3vl_8b_int8_convrot.safetensors")
        self.assertEqual(PE_REPO, "pottokao/Qwen-Image-2.1-PE-I2I-Heretic-GGUF")
        self.assertEqual(PE_FILE, "pe_i2i_heretic-Q6_K.gguf")
        self.assertEqual(PE_VISION_FILE, "pe_i2i_heretic.mmproj-bf16.gguf")

    def test_pe_quantization_respects_available_vram(self):
        with patch("neveai.routers.image_quality_generation._detected_gpu_vram_mib", return_value=16384):
            self.assertEqual(_pe_file_for_hardware(), PE_FILE)
        with patch("neveai.routers.image_quality_generation._detected_gpu_vram_mib", return_value=8192):
            self.assertEqual(_pe_file_for_hardware(), PE_LOW_VRAM_FILE)
        with patch("neveai.routers.image_quality_generation._detected_gpu_vram_mib", return_value=None):
            self.assertEqual(_pe_file_for_hardware(), PE_LOW_VRAM_FILE)


if __name__ == "__main__":
    unittest.main()
