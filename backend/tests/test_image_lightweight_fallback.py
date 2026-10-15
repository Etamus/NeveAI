import subprocess
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from neveai.routers import stable_diffusion as sd


class ImageFallbackPolicyTests(unittest.TestCase):
    def test_memory_probe_uses_selected_cuda_gpu_instead_of_largest_gpu(self):
        with patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'), \
                patch.object(sd.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '8192\n')) as probe, \
                patch.dict('os.environ', {'CUDA_VISIBLE_DEVICES': '1,0'}):
            self.assertEqual(sd._detected_gpu_vram_mib(selected_only=True), 8192)
            self.assertIn('--id=1', probe.call_args.args[0])

    def test_old_image_choice_migrates_to_image15(self):
        for value in ('neve_image', None, 'invalid'):
            self.assertEqual(sd.normalize_image_quality(value), 'neve_image_2')

    def test_only_small_or_unknown_hardware_uses_lightweight_generation(self):
        for memory, expected in ((None, True), (0, True), (4096, True), (8191, True),
                                 (8192, False), (8193, False), (11264, False),
                                 (12288, False), (16303, False), (24576, False)):
            with self.subTest(memory=memory), patch.object(sd, '_detected_gpu_vram_mib', return_value=memory):
                self.assertEqual(sd._use_lightweight_zimage('neve_image_2', False), expected)
                self.assertFalse(sd._use_lightweight_zimage('neve_image_2', True))
                self.assertFalse(sd._use_lightweight_zimage('qwen_image_2s', False))
                self.assertFalse(sd._use_lightweight_zimage(sd.QWEN_IMAGE_21_OFFICIAL_QUALITY, False))

    def test_cpu_detection_selects_lightweight_without_assuming_gpu_memory(self):
        with patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cpu'), \
                patch.object(sd.subprocess, 'run') as probe:
            self.assertIsNone(sd._detected_gpu_vram_mib(selected_only=True))
            self.assertTrue(sd._use_lightweight_zimage('neve_image_2', False))
            probe.assert_not_called()

    def test_lightweight_canvas_supports_all_ratios_without_oversizing(self):
        for ratio in sd.QUALITY_IMAGE_RESOLUTIONS:
            with self.subTest(ratio=ratio):
                width, height = sd.lightweight_image_dimensions(ratio)
                self.assertLessEqual(max(width, height), 768)
                self.assertEqual(width % 64, 0)
                self.assertEqual(height % 64, 0)
                original = sd.quality_image_dimensions(ratio)
                self.assertLess(abs(width / height - original[0] / original[1]), .1)


class ImageFallbackLoadingTests(unittest.IsolatedAsyncioTestCase):
    async def test_lightweight_generation_keeps_styles_and_applies_offload_and_small_canvas(self):
        import tempfile
        from types import SimpleNamespace
        pipeline = sd._ZImageTurboPipeline()
        pipeline._quality = 'neve_image_2'
        pipeline._lightweight_generation = True
        pipeline._resources = sd._ZImageResources(Path('sd-cli'), Path(sd.ZIMAGE_GGUF_FILE),
                                                Path(sd.ZIMAGE_UNCENSORED_LLM_FILE), Path('vae'))
        process = SimpleNamespace(returncode=0, stdout=None, stderr=None, wait=AsyncMock(return_value=0))
        commands=[]
        async def execute(*command, **kwargs):
            commands.append(command)
            Path(command[command.index('-o') + 1]).write_bytes(b'isolated-png-fixture')
            return process
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(sd, 'IMAGE_OUTPUT_DIR', Path(temporary)), \
                patch.object(sd, '_prepare_image_prompt', AsyncMock(return_value='A landscape')), \
                patch.object(sd, '_prepare_init_image', AsyncMock(return_value=None)), \
                patch.object(sd, '_ensure_style_lora', return_value=Path('minimalist.safetensors')), \
                patch.object(sd.asyncio, 'create_subprocess_exec', side_effect=execute):
            dimensions=AsyncMock()
            result=await pipeline.generate('Landscape', resolution='9:16', style='minimalist', dimensions_callback=dimensions)
            self.assertTrue(result.startswith('data:image/png;base64,'))
            command=commands[0]
            self.assertIn('--offload-to-cpu', command)
            self.assertNotIn('--vae-conv-direct', command)
            self.assertEqual(int(command[command.index('-H') + 1]), 768)
            self.assertLess(int(command[command.index('-W') + 1]), 768)
            self.assertIn('<lora:minimalist:1>', command[command.index('-p') + 1])
            dimensions.assert_awaited_once_with(*sd.lightweight_image_dimensions('9:16'))

    async def test_model_loading_keeps_styles_encoder_and_switches_quantization_with_hardware(self):
        pipeline = sd._ZImageTurboPipeline()
        with patch.object(sd, '_ensure_sd_cli_binary', return_value=Path('sd-cli')), \
                patch('huggingface_hub.hf_hub_download', side_effect=lambda **kw: kw['filename']) as download, \
                patch.object(sd, '_detected_gpu_vram_mib', return_value=8191) as memory:
            await pipeline.load(sd.ZIMAGE_REPO, quality='neve_image_2')
            self.assertTrue(pipeline._lightweight_generation)
            self.assertEqual(pipeline._quality, 'neve_image_2')
            self.assertEqual(pipeline._resources.diffusion_model.name, sd.ZIMAGE_GGUF_FILE)
            self.assertEqual(pipeline._resources.llm.name, sd.ZIMAGE_UNCENSORED_LLM_FILE)
            count = download.call_count
            await pipeline.load(sd.ZIMAGE_REPO, quality='neve_image_2')
            self.assertEqual(download.call_count, count)
            memory.return_value = 8192
            await pipeline.load(sd.ZIMAGE_REPO, quality='neve_image_2')
            self.assertFalse(pipeline._lightweight_generation)
            self.assertEqual(pipeline._resources.diffusion_model.name, sd.ZIMAGE_QUALITY_GGUF_FILE)
            self.assertEqual(pipeline._resources.llm.name, sd.ZIMAGE_UNCENSORED_LLM_FILE)
            memory.return_value = None
            await pipeline.load(sd.ZIMAGE_REPO, quality='neve_image_2')
            self.assertTrue(pipeline._lightweight_generation)
            self.assertEqual(pipeline._resources.diffusion_model.name, sd.ZIMAGE_GGUF_FILE)
            memory.return_value = None
            await pipeline.load(sd.ZIMAGE_REPO, quality='neve_image_2', edit=True)
            self.assertFalse(pipeline._lightweight_generation)
            self.assertEqual(pipeline._resources.diffusion_model.name, sd.MAGEFLOW_EDIT_FILE)
            await pipeline.unload()
            self.assertFalse(pipeline._lightweight_generation)


if __name__ == '__main__': unittest.main()
