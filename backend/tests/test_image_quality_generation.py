import io
import unittest
import subprocess
import tempfile
from pathlib import Path
import httpx
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from PIL import Image

from neveai.routers.image_quality_generation import (
    ENCODER_FILE,
    EDIT_MODEL_FILE,
    VAE_FILE,
    PE_SYSTEM_FILE,
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
    _prefer_int8_edit,
    _install_cfg1_node,
    CFG1_NODE_FILE,
    _fit_balanced_reference,
    _fit_optimized_reference,
    OPTIMIZED_EDIT_STEPS,
    _sampling_progress,
)
from neveai.routers.stable_diffusion import (
    QWEN_IMAGE_21_OFFICIAL_QUALITY,
    normalize_image_quality,
)


class NeveImage21ComfyTests(unittest.TestCase):
    def test_branding_and_retired_profile_preserve_quality_runtime(self):
        self.assertEqual(NeveImage21Runtime.NAME, "Neve Image 2.6")
        self.assertEqual(normalize_image_quality("qwen_image_2_2_experimental"),
                         QWEN_IMAGE_21_OFFICIAL_QUALITY)
        self.assertEqual(normalize_image_quality(QWEN_IMAGE_21_OFFICIAL_QUALITY),
                         QWEN_IMAGE_21_OFFICIAL_QUALITY)

    def test_detailed_edits_retain_source_pixels_without_changing_legacy_fit(self):
        self.assertEqual(_fit_reference(1913, 1077), (1536, 864))
        self.assertEqual(_fit_reference(1913, 1077, detailed_edit=True), (1920, 1088))
        self.assertEqual(_fit_reference(1672, 941, detailed_edit=True), (1664, 928))
        self.assertEqual(_fit_reference(512, 512, detailed_edit=True), _fit_reference(512, 512))
        for width, height in ((8192, 8192), (4096, 8192), (8192, 4096), (1920, 1080)):
            with self.subTest(size=(width, height)):
                fitted = _fit_reference(width, height, detailed_edit=True)
                self.assertLessEqual(max(fitted), 2048)
                self.assertLessEqual(fitted[0] * fitted[1], 2048 * 1024 * 1.03)
                self.assertTrue(all(side % 32 == 0 for side in fitted))

    def test_int8_edit_graph_preserves_native_conditioning_and_sampler(self):
        graph = NeveImage21Runtime.build_workflow('Edit image 1 using image 2', 1920, 1088,
                                                 ['canvas.png', 'style.png'], 42, model_file=EDIT_MODEL_FILE)
        self.assertEqual(graph['1'], {'class_type': 'UNETLoader', 'inputs': {'unet_name': EDIT_MODEL_FILE, 'weight_dtype': 'default'}})
        self.assertEqual(graph['4']['inputs']['vae'], ['3', 0])
        self.assertEqual(graph['4']['inputs']['resolution'], 0)
        self.assertEqual(graph['5']['inputs']['latent_image'], ['4', 2])
        self.assertEqual(graph['5']['inputs']['cfg'], 1.0)
        self.assertEqual(graph['5']['inputs']['steps'], 40)
        self.assertEqual(graph['2']['inputs']['clip_name'], ENCODER_FILE)
        self.assertEqual(graph['4']['class_type'], 'NeveTextEncodeQwenImage21CFG1')

    def test_cfg1_extension_is_installed_idempotently_without_touching_other_nodes(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch('neveai.routers.image_quality_generation.fast.CUSTOM_NODES_DIR', Path(temporary)):
            custom = Path(temporary) / 'user_node.py'
            custom.write_text('custom')
            target = Path(temporary) / CFG1_NODE_FILE
            _install_cfg1_node()
            signature = (target.read_bytes(), target.stat().st_mtime_ns)
            _install_cfg1_node()
            self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), signature)
            self.assertEqual(custom.read_text(), 'custom')
            self.assertFalse(target.with_suffix('.tmp').exists())

    def test_int8_edit_policy_only_enables_validated_gpu_and_reference_budget(self):
        for output, expected in [('16303, 12.0\n', True), ('16384, 8.6\n', True),
                                 ('12288, 8.6\n', False), ('24576, 7.5\n', False),
                                 ('8192, 12.0\n', False), ('unknown\n', False), ('', False)]:
            with self.subTest(output=output), patch('neveai.routers.image_quality_generation.os.name', 'nt'), \
                    patch('neveai.routers.image_quality_generation.shutil.which', return_value='nvidia-smi'), \
                    patch('neveai.routers.image_quality_generation.psutil.virtual_memory', return_value=SimpleNamespace(total=32 * 1024**3)), \
                    patch('neveai.routers.image_quality_generation.subprocess.run', return_value=subprocess.CompletedProcess([], 0, output)):
                self.assertEqual(_prefer_int8_edit(2), expected)
                self.assertEqual(_prefer_int8_edit(3), expected)
                self.assertFalse(_prefer_int8_edit(0))
                self.assertEqual(_prefer_int8_edit(4), expected)
                self.assertEqual(_prefer_int8_edit(5), expected)
                self.assertEqual(_prefer_int8_edit(6), expected)
                self.assertEqual(_prefer_int8_edit(10), expected)
                self.assertFalse(_prefer_int8_edit(11))

    def test_four_reference_profile_keeps_small_ram_hardware_on_existing_path(self):
        with patch('neveai.routers.image_quality_generation.os.name', 'nt'), \
                patch('neveai.routers.image_quality_generation.shutil.which', return_value='nvidia-smi'), \
                patch('neveai.routers.image_quality_generation.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '16303, 12.0')) as probe, \
                patch('neveai.routers.image_quality_generation.psutil.virtual_memory', return_value=SimpleNamespace(total=16 * 1024**3)):
            self.assertFalse(_prefer_int8_edit(4))
            self.assertFalse(_prefer_int8_edit(5))
            self.assertTrue(_prefer_int8_edit(3))
            self.assertEqual(probe.call_count, 1)

    def test_ram_probe_failure_keeps_original_four_reference_fallback(self):
        with patch('neveai.routers.image_quality_generation.os.name', 'nt'), \
                patch('neveai.routers.image_quality_generation.shutil.which', return_value='nvidia-smi'), \
                patch('neveai.routers.image_quality_generation.psutil.virtual_memory', side_effect=OSError('unavailable')):
            self.assertFalse(_prefer_int8_edit(4))

    def test_balanced_four_reference_budget_preserves_primary_detail(self):
        expected = [(2368, 1344), (480, 736), (480, 704), (800, 448)]
        sources = [(1917, 1079), (145, 221), (186, 266), (1672, 941)]
        actual = [_fit_balanced_reference(*size, index) for index, size in enumerate(sources)]
        self.assertEqual(actual, expected)
        self.assertEqual(_fit_balanced_reference(512, 512, 0), _fit_reference(512, 512))
        smaller = _fit_balanced_reference(1368, 960, 0)
        larger = _fit_balanced_reference(1390, 960, 0)
        self.assertLess(larger[0] * larger[1] / (smaller[0] * smaller[1]), 1.15)
        self.assertLess(sum(width * height for width, height in actual), 4.2 * 1024**2)
        for source in [(16384, 16384), (30000, 128), (128, 30000), (1, 1)]:
            for index in range(4):
                width, height = _fit_balanced_reference(*source, index)
                self.assertTrue(width % 32 == height % 32 == 0)
                self.assertLessEqual(max(width, height), 2560)
                budget = 3 * 1024**2 if not index else 1024**2 / 3
                self.assertLessEqual(width * height, budget * 1.1)
        runtime = NeveImage21Runtime()
        self.assertEqual(runtime._reference_size(1917, 1079, EDIT_MODEL_FILE, 0, 4), expected[0])
        self.assertEqual(runtime._reference_size(1917, 1079, MODEL_FILE, 0, 4), _fit_reference(1917, 1079))
        with patch('neveai.routers.image_quality_generation.psutil.virtual_memory',
                   return_value=SimpleNamespace(total=32 * 1024**3)):
            self.assertEqual(runtime._reference_size(1917, 1079, EDIT_MODEL_FILE, 0, 2), expected[0])

    def test_balanced_graph_uses_lossless_cpu_cache_for_four_to_ten_reference_int8(self):
        for model in [MODEL_FILE, EDIT_MODEL_FILE]:
            for count in [0, 1, 2, 3, 4, 5, 6, 10]:
                graph = NeveImage21Runtime.build_workflow('Edit', 2368, 1344, [f'{i}.png' for i in range(count)], 42, model_file=model)
                if model == EDIT_MODEL_FILE and 4 <= count <= 10:
                    self.assertEqual(graph['5']['inputs']['model'], ['30', 0])
                    self.assertEqual(graph['30']['inputs'], {'model': ['1', 0], 'device': 'cpu', 'dtype': 'default'})
                else:
                    self.assertNotIn('30', graph)
                self.assertEqual(graph['5']['inputs']['steps'], 40)
                self.assertEqual(graph['5']['inputs']['cfg'], 1)

    def test_five_reference_budget_is_bounded_without_changing_four_reference_sizes(self):
        runtime = NeveImage21Runtime()
        sources = [(1917, 1079), (145, 221), (186, 266), (1672, 941), (2368, 1344)]
        fitted = [runtime._reference_size(*size, EDIT_MODEL_FILE, index, 5)
                  for index, size in enumerate(sources)]
        self.assertEqual(fitted[0], (2368, 1344))
        self.assertLessEqual(sum(w * h for w, h in fitted), 4.2 * 1024**2)
        self.assertTrue(all(w % 32 == h % 32 == 0 for w, h in fitted))
        self.assertLessEqual(sum(w * h for w, h in fitted[1:]), 1.1 * 1024**2)
        self.assertEqual(runtime._reference_size(*sources[0], MODEL_FILE, 0, 6),
                         _fit_reference(*sources[0]))
        for count in (0, 11):
            with self.assertRaises(ValueError):
                _fit_balanced_reference(512, 512, 0, count)

    def test_detail_canvas_increases_only_primary_input_and_keeps_planner_budget(self):
        runtime = NeveImage21Runtime()
        with patch('neveai.routers.image_quality_generation.psutil.virtual_memory',
                   return_value=SimpleNamespace(total=32 * 1024**3)):
            for count in (1, 2, 3):
                for index in range(count):
                    for size in ((1920, 1088), (1672, 941), (512, 512), (8192, 8192)):
                        with self.subTest(count=count, index=index, size=size):
                            fitted = runtime._reference_size(*size, EDIT_MODEL_FILE, index, count)
                            expected = (_fit_balanced_reference(*size, index, count) if index == 0
                                        else _fit_reference(*size, detailed_edit=True))
                            self.assertEqual(fitted, expected)
                            self.assertLessEqual(fitted[0] * fitted[1], 3.1 * 1024**2)
                            self.assertEqual(runtime._reference_size(*size, EDIT_MODEL_FILE, index, count,
                                                                    detail_canvas=False),
                                             _fit_reference(*size, detailed_edit=True))

    def test_smaller_or_unknown_ram_keeps_existing_one_to_three_reference_budget(self):
        runtime = NeveImage21Runtime()
        for probe in (SimpleNamespace(total=16 * 1024**3), SimpleNamespace(total=24 * 1024**3),
                      OSError('unavailable')):
            kwargs = {'side_effect': probe} if isinstance(probe, Exception) else {'return_value': probe}
            with patch('neveai.routers.image_quality_generation.psutil.virtual_memory', **kwargs):
                for count in (1, 2, 3):
                    self.assertEqual(runtime._reference_size(1920, 1088, EDIT_MODEL_FILE, 0, count),
                                     _fit_reference(1920, 1088, detailed_edit=True))
        self.assertEqual(runtime._reference_size(1920, 1088, MODEL_FILE, 0, 2),
                         _fit_reference(1920, 1088))

    def test_int8_limit_matches_all_reference_counts(self):
        with patch('neveai.routers.image_quality_generation.os.name', 'nt'), \
                patch('neveai.routers.image_quality_generation.shutil.which', return_value='nvidia-smi'), \
                patch('neveai.routers.image_quality_generation.psutil.virtual_memory',
                      return_value=SimpleNamespace(total=32 * 1024**3)), \
                patch('neveai.routers.image_quality_generation.subprocess.run',
                      return_value=subprocess.CompletedProcess([], 0, '16303, 12.0')), \
                patch.dict('os.environ', {'CUDA_VISIBLE_DEVICES': '0'}):
            for count in range(12):
                self.assertEqual(_prefer_int8_edit(count), 1 <= count <= 10)

    def test_gpu_probe_failure_preserves_legacy_generation(self):
        with patch('neveai.routers.image_quality_generation.os.name', 'nt'), \
                patch('neveai.routers.image_quality_generation.shutil.which', return_value='nvidia-smi'), \
                patch('neveai.routers.image_quality_generation.subprocess.run', side_effect=subprocess.TimeoutExpired('nvidia-smi', 10)):
            self.assertFalse(_prefer_int8_edit(1))
        with patch('neveai.routers.image_quality_generation.shutil.which', return_value=None):
            self.assertFalse(_prefer_int8_edit(2))
        with patch.dict('os.environ', {'CUDA_VISIBLE_DEVICES': '1'}):
            self.assertFalse(_prefer_int8_edit(2))

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


class NeveImage21OptimizedEditingTests(unittest.TestCase):
    def test_single_reference_keeps_cfg1_and_full_progress_without_an_unused_second_sampler(self):
        graph = NeveImage21Runtime.build_workflow('Edit', 2368, 1344, ['source.png'], 123,
                                                  EDIT_MODEL_FILE, optimized_edit=True)
        self.assertNotIn('32', graph)
        self.assertEqual(graph['4']['class_type'], 'NeveTextEncodeQwenImage21CFG1')
        self.assertEqual(graph['5']['class_type'], 'KSampler')
        self.assertEqual(graph['5']['inputs']['steps'], OPTIMIZED_EDIT_STEPS)
        self.assertEqual(graph['5']['inputs']['cfg'], 1)
        self.assertEqual(graph['5']['inputs']['seed'], 123)
        self.assertEqual(graph['5']['inputs']['model'], ['30', 0])
        self.assertEqual(graph['7']['inputs']['samples'], ['5', 0])
        self.assertEqual(_fit_optimized_reference(2368, 1344, 0, 1), (2368, 1344))
        self.assertEqual(_fit_optimized_reference(992, 1344, 0, 1), (1248, 1696))
        self.assertEqual(_sampling_progress({'node': '5', 'value': 25, 'max': 25},
                                            optimized_edit=True), 94)
        for node in ('4', '7', '32'):
            self.assertIsNone(_sampling_progress({'node': node, 'value': 25, 'max': 25},
                                                 optimized_edit=True))

    def test_progress_tracks_sampling_and_ignores_loading_and_decode_events(self):
        values = [_sampling_progress({'node': '5', 'value': step, 'max': OPTIMIZED_EDIT_STEPS}, optimized_edit=True)
                  for step in range(1, OPTIMIZED_EDIT_STEPS + 1)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[-1], 94)
        self.assertTrue(all(value < 94 for value in values[:-1]))
        for node in ('1', '4', '7', '32', None):
            self.assertIsNone(_sampling_progress({'node': node, 'value': 100, 'max': 100}, optimized_edit=True))
        self.assertIsNone(_sampling_progress({'value': 1, 'max': 0}, optimized_edit=True))
        self.assertIsNone(_sampling_progress({}))
        self.assertIsNone(_sampling_progress({'max': None}))
        self.assertEqual(_sampling_progress({'value': 5, 'max': 10}), 67)

    def test_quality_profile_uses_native_cfg1_sampling_for_all_reference_counts(self):
        for count in range(2, 11):
            with self.subTest(count=count):
                graph = NeveImage21Runtime.build_workflow('Edit', 1920, 1088,
                    [f'{index}.png' for index in range(count)], 123, EDIT_MODEL_FILE, optimized_edit=True)
                sampling = graph['5']['inputs']
                self.assertNotIn('32', graph)
                self.assertEqual(graph['4']['class_type'], 'NeveTextEncodeQwenImage21CFG1')
                self.assertEqual(graph['4']['inputs']['negative_prompt'], '')
                self.assertEqual(graph['30']['inputs'], {'model': ['1', 0], 'device': 'cpu', 'dtype': 'default'})
                self.assertEqual(graph['5']['class_type'], 'KSampler')
                self.assertEqual(sampling['latent_image'], ['4', 2])
                self.assertEqual(sampling['model'], ['30', 0])
                self.assertEqual(sampling['positive'], ['4', 0])
                self.assertEqual(sampling['negative'], ['4', 1])
                self.assertEqual(sampling['cfg'], 1)
                self.assertEqual(sampling['seed'], 123)
                self.assertEqual(sampling['steps'], OPTIMIZED_EDIT_STEPS)
                self.assertEqual(sampling['sampler_name'], 'euler')
                self.assertEqual(sampling['scheduler'], 'simple')
                self.assertEqual(sampling['denoise'], 1)
                self.assertEqual(graph['7']['inputs']['samples'], ['5', 0])
                self.assertEqual(graph['3']['inputs']['vae_name'], VAE_FILE)
                for index in range(count):
                    self.assertEqual(graph['4']['inputs'][f'images.image_{index + 1}'], [str(index + 9), 0])

    def test_legacy_paths_and_text_to_image_ignore_optimized_edit_flag(self):
        for model, references in ((MODEL_FILE, ['1.png', '2.png']), (MODEL_FILE, []), (EDIT_MODEL_FILE, [])):
            args = ('A flower', 1216, 704, references, 123, model)
            self.assertEqual(NeveImage21Runtime.build_workflow(*args),
                             NeveImage21Runtime.build_workflow(*args, optimized_edit=True))

    def test_budget_is_bounded_for_one_through_ten_references_and_all_orientations(self):
        runtime = NeveImage21Runtime()
        for count in range(1, 11):
            for size in ((1918, 1076), (992, 1344), (512, 512), (8192, 8192), (8192, 256)):
                with self.subTest(count=count, size=size):
                    sizes = [_fit_optimized_reference(*size, index, count) for index in range(count)]
                    self.assertLessEqual(sizes[0][0] * sizes[0][1], 3.1 * 1024**2)
                    if count >= 4:
                        self.assertLessEqual(sum(w * h for w, h in sizes[1:]), 1.1 * 1024**2)
                    else:
                        self.assertTrue(all(w * h <= 2.1 * 1024**2 for w, h in sizes[1:]))
                    self.assertTrue(all(w % 32 == h % 32 == 0 and min(w, h) >= 32 and max(w, h) <= 2560
                                        for w, h in sizes))
                    for index in range(count):
                        self.assertEqual(runtime._reference_size(*size, EDIT_MODEL_FILE, index, count,
                                                                  detail_canvas=False, optimized_edit=True),
                                         runtime._reference_size(*size, EDIT_MODEL_FILE, index, count,
                                                                  detail_canvas=False))
        self.assertEqual(_fit_optimized_reference(1918, 1076, 0, 3), (2368, 1344))
        self.assertLess(_fit_optimized_reference(512, 512, 0, 1)[0], 1440)
        for args in ((0, 512, 0, 1), (512, 512, 0, 0), (512, 512, 0, 11), (512, 512, 2, 2)):
            with self.assertRaises(ValueError):
                _fit_optimized_reference(*args)

    def test_quality_profile_preserves_pre_optimization_reference_detail(self):
        for count in range(1, 11):
            for index in range(count):
                for size in ((145, 221), (186, 266), (1917, 1079), (3840, 2160)):
                    with self.subTest(count=count, index=index, size=size):
                        expected = (_fit_balanced_reference(*size, index, count)
                                    if index == 0 or count >= 4 else _fit_reference(*size, detailed_edit=True))
                        self.assertEqual(_fit_optimized_reference(*size, index, count), expected)

    def test_quality_sampling_matches_pre_optimization_except_lossless_cache(self):
        self.assertEqual(OPTIMIZED_EDIT_STEPS, STEPS)
        for count in range(1, 11):
            with self.subTest(count=count):
                args = ('Edit', 2368, 1344, [f'{index}.png' for index in range(count)], 42, EDIT_MODEL_FILE)
                expected = NeveImage21Runtime.build_workflow(*args)
                expected['30'] = {'class_type': 'QwenImage21Cache', 'inputs': {
                    'model': ['1', 0], 'device': 'cpu', 'dtype': 'default',
                }}
                expected['5']['inputs']['model'] = ['30', 0]
                self.assertEqual(NeveImage21Runtime.build_workflow(*args, optimized_edit=True), expected)

    def test_hardware_gate_and_memory_recovery_keep_legacy_profiles(self):
        runtime = NeveImage21Runtime()
        prefix = 'neveai.routers.image_quality_generation.'
        for ram, expected in ((32, True), (24, False), (16, False)):
            with patch(prefix + 'psutil.virtual_memory', return_value=SimpleNamespace(total=ram * 1024**3)):
                self.assertEqual(runtime._optimized_edit_available(EDIT_MODEL_FILE), expected)
                self.assertFalse(runtime._optimized_edit_available(MODEL_FILE))
                for attribute in ('_force_gguf', '_cpu_mode', '_memory_saver'):
                    setattr(runtime, attribute, True)
                    self.assertFalse(runtime._optimized_edit_available(EDIT_MODEL_FILE))
                    setattr(runtime, attribute, False)
        with patch(prefix + 'psutil.virtual_memory', side_effect=OSError('unavailable')):
            self.assertFalse(runtime._optimized_edit_available(EDIT_MODEL_FILE))


class NeveImage21ModelPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_detail_canvas_preserves_legacy_planner_pixels_prompt_and_reference_order(self):
        prefix = 'neveai.routers.image_quality_generation.'
        class WorkflowCaptured(Exception):
            pass

        sources = []
        for index in range(10):
            size = ((1917, 1079), (1672, 941), (512, 512))[min(index, 2)]
            gradient = Image.linear_gradient('L').resize(size).convert('RGB')
            tint = Image.new('RGB', size, (index * 23, 255 - index * 19, index * 17))
            image = Image.blend(gradient, tint, 0.5)
            sources.append(image)
        prompt = 'Use image 2 only as the style of image 1; preserve its background.'
        rewritten = 'Edit <image1> using only the rendering style of <image2>.'
        for count, model, cpu, saver, cached in [
            (1, EDIT_MODEL_FILE, False, False, False),
            (2, EDIT_MODEL_FILE, False, False, False),
            (3, EDIT_MODEL_FILE, False, False, False),
            (4, EDIT_MODEL_FILE, False, False, False),
            (10, EDIT_MODEL_FILE, False, False, False),
            (2, MODEL_FILE, False, False, False),
            (6, MODEL_FILE, False, False, False),
            (2, MODEL_FILE, True, True, False),
            (4, MODEL_FILE, False, True, False),
            (2, EDIT_MODEL_FILE, False, False, True),
        ]:
            with self.subTest(count=count, model=model, cpu=cpu, saver=saver, cached=cached), \
                    tempfile.TemporaryDirectory() as temporary:
                runtime = NeveImage21Runtime()
                runtime._cpu_mode, runtime._memory_saver = cpu, saver
                runtime._retry_prompt = rewritten if cached else None
                originals, expected_planning, expected_uploads = [], [], []
                with patch(prefix + 'psutil.virtual_memory', return_value=SimpleNamespace(total=32 * 1024**3)):
                    optimized = runtime._optimized_edit_available(model)
                    from neveai.routers.image_quality_generation import _adaptive_auxiliary_sizes
                    adaptive = (_adaptive_auxiliary_sizes([image.size for image in sources[1:count]])
                                if optimized and count >= 4 else None)
                    for index in range(count):
                        image = sources[index]
                        original = io.BytesIO()
                        image.save(original, format='PNG')
                        originals.append(original.getvalue())
                        planning_size = (_fit_reference(*image.size, detailed_edit=model == EDIT_MODEL_FILE)
                                         if count < 4 and not saver else
                                         runtime._reference_size(*image.size, model, index, count, detail_canvas=False))
                        for size, target in [
                            (planning_size, expected_planning),
                            (adaptive[index - 1] if adaptive is not None and index > 0 else
                             runtime._reference_size(*image.size, model, index, count, optimized_edit=optimized), expected_uploads),
                        ]:
                            output = io.BytesIO()
                            image.resize(size, Image.Resampling.LANCZOS).save(output, format='PNG')
                            target.append(output.getvalue())
                    uploads = []
                    async def post(url, **kwargs):
                        if url == '/upload/image':
                            uploads.append(kwargs['files']['image'][1])
                            return httpx.Response(200, json={'name': f'unit-{len(uploads)}.png'},
                                                  request=httpx.Request('POST', 'http://localhost/upload/image'))
                        self.assertEqual(url, '/prompt')
                        expected_graph = runtime.build_workflow(
                            rewritten, 512, 512, [f'unit-{i + 1}.png' for i in range(count)], 42,
                            model_file=model, optimized_edit=optimized)
                        if expected_graph['4']['class_type'] == 'NeveTextEncodeQwenImage21CFG1' and not runtime._cfg1_node_ready:
                            expected_graph['4']['class_type'] = 'TextEncodeQwenImage21'
                        self.assertEqual(kwargs['json']['prompt'], expected_graph)
                        self.assertEqual(runtime._generation_details, {
                            'effective_prompt': expected_graph['4']['inputs']['prompt'],
                            'seed': '42', 'model_file': model, 'reference_count': count,
                            'steps': expected_graph['5']['inputs']['steps'],
                        })
                        raise WorkflowCaptured()
                    client = AsyncMock()
                    client.__aenter__.return_value = client
                    client.post.side_effect = post
                    dimensions = AsyncMock()
                    with patch.object(runtime, '_ensure_models', AsyncMock(return_value=model)), \
                            patch.object(runtime, '_plan_edit', AsyncMock(return_value=rewritten)) as planner, \
                            patch.object(runtime, '_start_comfy', AsyncMock(return_value='http://localhost')), \
                            patch.object(runtime, '_stop', AsyncMock()), \
                            patch(prefix + '_read_image_reference_bytes', side_effect=originals), \
                            patch(prefix + 'httpx.AsyncClient', return_value=client), \
                            patch(prefix + 'fast.INPUT_DIR', Path(temporary)), \
                            patch(prefix + 'os.name', 'nt'):
                        with self.assertRaises(WorkflowCaptured):
                            await runtime._run_once(prompt, 'auto', ['ref'] * count, None, AsyncMock(),
                                                    dimensions, cpu_mode=cpu, memory_saver=saver, seed=42)
                    if cached:
                        planner.assert_not_awaited()
                    else:
                        self.assertEqual(planner.await_args.args[:2], (prompt, expected_planning))
                    self.assertEqual(uploads, expected_uploads)
                    with Image.open(io.BytesIO(expected_uploads[0])) as image:
                        dimensions.assert_awaited_once_with(*image.size)

    async def test_real_selection_boundary_and_basic_hardware_need_no_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for subdir, filename in [('diffusion_models', MODEL_FILE), ('diffusion_models', EDIT_MODEL_FILE),
                                     ('text_encoders', ENCODER_FILE), ('vae', VAE_FILE), ('pe', PE_FILE),
                                     ('pe', PE_VISION_FILE), ('pe', PE_SYSTEM_FILE)]:
                path = root / subdir / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'x' * 1280)
            prefix = 'neveai.routers.image_quality_generation.'
            with patch(prefix + 'fast.MODELS_DIR', root), patch(prefix + 'PE_DIR', root / 'pe'), \
                    patch(prefix + 'EDIT_MODEL_BYTES', 1280), patch(prefix + 'os.name', 'nt'), \
                    patch(prefix + 'shutil.which', return_value='nvidia-smi'), \
                    patch(prefix + 'psutil.virtual_memory', return_value=SimpleNamespace(total=32 * 1024**3)), \
                    patch(prefix + '_pe_file_for_hardware', return_value=PE_FILE), \
                    patch(prefix + 'fast.neve_image_2s_runtime._install', new_callable=AsyncMock), \
                    patch(prefix + '_install_cfg1_node'), \
                    patch(prefix + 'hf_hub_download') as download, \
                    patch.dict('os.environ', {'CUDA_VISIBLE_DEVICES': '0'}):
                for vram, count, expected in [('16303, 12.0', 5, EDIT_MODEL_FILE),
                                              ('16303, 12.0', 10, EDIT_MODEL_FILE),
                                              ('8192, 12.0', 1, MODEL_FILE),
                                              ('8192, 12.0', 5, MODEL_FILE)]:
                    with self.subTest(vram=vram, count=count), patch(prefix + 'subprocess.run',
                            return_value=subprocess.CompletedProcess([], 0, vram)):
                        runtime = NeveImage21Runtime()
                        self.assertEqual(await runtime._ensure_models(AsyncMock(), True, count), expected)
                download.assert_not_called()

    async def test_int8_download_failure_keeps_existing_gguf_and_planner(self):
        await self._check_preparation(False)

    async def test_valid_int8_uses_existing_companions_without_redownloading(self):
        await self._check_preparation(True)

    async def test_incomplete_int8_offline_keeps_existing_gguf(self):
        await self._check_preparation(False, incomplete=True)

    async def test_optional_cfg1_install_failure_keeps_selected_model(self):
        await self._check_preparation(True, node_failure=True)

    async def _check_preparation(self, installed, incomplete=False, node_failure=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for subdir, filename in [('diffusion_models', MODEL_FILE), ('text_encoders', ENCODER_FILE),
                                     ('vae', VAE_FILE), ('pe', PE_FILE), ('pe', PE_VISION_FILE), ('pe', PE_SYSTEM_FILE)]:
                path = root / subdir / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'x' * 1280)
            if installed:
                (root / 'diffusion_models' / EDIT_MODEL_FILE).write_bytes(b'x' * 1280)
            elif incomplete:
                (root / 'diffusion_models' / EDIT_MODEL_FILE).write_bytes(b'x' * 128)
            prefix = 'neveai.routers.image_quality_generation.'
            progress = AsyncMock()
            with patch(prefix + 'fast.MODELS_DIR', root), patch(prefix + 'PE_DIR', root / 'pe'), \
                    patch(prefix + 'EDIT_MODEL_BYTES', 1280), patch(prefix + '_prefer_int8_edit', return_value=True), \
                    patch(prefix + '_pe_file_for_hardware', return_value=PE_FILE), \
                    patch(prefix + 'fast.neve_image_2s_runtime._install', new_callable=AsyncMock), \
                    patch(prefix + '_install_cfg1_node', side_effect=PermissionError('read only') if node_failure else None), \
                    patch(prefix + 'hf_hub_download', side_effect=httpx.ConnectError('offline')) as download:
                runtime = NeveImage21Runtime()
                result = await runtime._ensure_models(progress, True, 2)
                self.assertEqual(result, EDIT_MODEL_FILE if installed else MODEL_FILE)
                self.assertEqual(runtime._cfg1_node_ready, installed and not node_failure)
                self.assertEqual(download.call_count, 0 if installed else 1)
                progress.assert_awaited_once_with(18)


if __name__ == "__main__":
    unittest.main()
