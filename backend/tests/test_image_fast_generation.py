import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from neveai.routers import image_fast_generation as fast
from neveai.routers import stable_diffusion as sd


class TurboWorkflowTests(unittest.TestCase):
    def test_checkpoint_and_schedule_replace_viggle_and_base_refinement(self):
        expected = [1, .978453, .95418, .926626, .89508, .845148, .704534, .414568, 0]
        self.assertEqual([float(x) for x in fast.SIGMAS.split(',')], expected)
        self.assertEqual(fast.TURBO_STEPS, 8)
        self.assertEqual(fast.MODEL_FILE, 'qwen_image_2.1_turbo_int8_convrot.safetensors')
        for refs in ([], ['a.png'], ['a.png', 'b.png', 'c.png'], [f'{i}.png' for i in range(10)]):
            with self.subTest(references=len(refs)):
                graph = fast.NeveImage2SRuntime.build_workflow('Uma cena', 1152, 1152, refs, 42)
                self.assertEqual(graph['1']['class_type'], 'UNETLoader')
                self.assertEqual(graph['1']['inputs']['unet_name'], fast.MODEL_FILE)
                self.assertEqual(graph['10']['class_type'], 'ManualSigmas')
                self.assertEqual(graph['10']['inputs']['sigmas'], fast.SIGMAS)
                self.assertEqual(graph['11']['inputs']['sigmas'], ['10', 0])
                self.assertEqual(graph['12']['inputs']['samples'], ['11', 0])
                self.assertEqual(graph['7']['class_type'], 'BasicGuider')
                self.assertEqual(graph['2']['inputs']['dtype'], 'default')
                self.assertEqual(graph['11']['inputs']['latent_image'], ['5', 2] if refs else ['6', 0])
                self.assertEqual(graph['5']['inputs']['resolution'], 0 if refs else 1024)
                types = [node['class_type'] for node in graph.values()]
                self.assertEqual(types.count('SamplerCustomAdvanced'), 1)
                self.assertFalse(any('Viggle' in item for item in types))
                self.assertNotIn('SplitSigmas', types)
                for node in graph.values():
                    for value in node['inputs'].values():
                        if isinstance(value, list):
                            self.assertIn(value[0], graph)
                for index, filename in enumerate(refs, 1):
                    link = graph['5']['inputs'][f'images.image_{index}']
                    self.assertEqual(graph[link[0]]['inputs']['image'], filename)

    def test_native_reference_tokens_and_roles_are_retained(self):
        graph = fast.NeveImage2SRuntime.build_workflow(
            'Use a imagem 1 como personagem e a imagem 2 como estilo',
            1152, 1152, ['first.png', 'second.png'], 42,
        )
        prompt = graph['5']['inputs']['prompt']
        self.assertIn('Use a <image1> como personagem', prompt)
        self.assertIn('<image2>', prompt)
        self.assertIn('Never substitute a subject', prompt)

    def test_too_many_references_are_rejected(self):
        with self.assertRaises(ValueError):
            fast.NeveImage2SRuntime.build_workflow('Scene', 1152, 1152, ['x'] * 11, 42)

    def test_reference_canvas_is_aligned_and_total_budget_is_bounded(self):
        for count in (1, 3, 10):
            sizes = [fast._reference_size(8000, 6000, index, count) for index in range(count)]
            self.assertLess(sum(w * h for w, h in sizes), 4.2 * 1024 * 1024)
            for width, height in sizes:
                self.assertEqual(width % 32, 0)
                self.assertEqual(height % 32, 0)
                self.assertLessEqual(max(width, height), 1536)
        self.assertEqual(fast._reference_size(1920, 1080, 0, 2), (1536, 864))

    def test_gpu_lock_is_shared_with_quality_profiles(self):
        from neveai.routers.image_quality_generation import neve_image_21_runtime
        self.assertIs(fast.neve_image_2s_runtime._lock, neve_image_21_runtime._lock)


class TurboAssetTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_shared_runtime_needs_no_viggle_or_package_reinstall(self):
        runtime = fast.NeveImage2SRuntime()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'main.py').touch()
            (root / 'python.exe').touch()
            (root / 'ComfyUI-GGUF').mkdir()
            (root / 'ComfyUI-GGUF/__init__.py').touch()
            marker = root / 'marker'
            marker.write_text('neve-image-2s-viggle-0.2.1-v3-comfy-0.38')
            with patch.object(fast, 'COMFY_DIR', root), patch.object(fast, 'CUSTOM_NODES_DIR', root), \
                    patch.object(fast, 'MARKER', marker), patch.object(fast, '_python', return_value=root / 'python.exe'), \
                    patch.object(runtime, '_command', AsyncMock()) as command:
                self.assertTrue(runtime.is_installed)
                await runtime._install(AsyncMock())
                command.assert_not_awaited()
                self.assertEqual(marker.read_text(), fast.RUNTIME_REVISION)

    async def test_assets_are_pinned_verified_and_reused(self):
        runtime = fast.NeveImage2SRuntime()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = b'known checkpoint'
            sha = hashlib.sha256(payload).hexdigest()
            assets = (('diffusion_models/model', len(payload), sha),)
            def download(**kwargs):
                target = root / kwargs['filename']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            with patch.object(fast, 'MODELS_DIR', root), patch.object(fast, 'MODEL_ASSETS', assets), \
                    patch('huggingface_hub.hf_hub_download', side_effect=download) as fetch, \
                    patch.object(fast, '_sha256', wraps=fast._sha256) as digest:
                await runtime._models(AsyncMock())
                await runtime._models(AsyncMock())
                self.assertTrue(runtime.models_ready)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(fetch.call_args.kwargs['revision'], fast.MODEL_REVISION)
                self.assertEqual(digest.call_count, 1)
                (root / assets[0][0]).write_bytes(b'bad checkpoint!')
                with self.assertRaises(RuntimeError):
                    await runtime._models(AsyncMock())
                self.assertEqual(fetch.call_count, 1)

    async def test_missing_or_corrupt_assets_never_fall_back_to_old_model(self):
        runtime = fast.NeveImage2SRuntime()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'model'
            with patch.object(fast, 'MODELS_DIR', root), \
                    patch.object(fast, 'MODEL_ASSETS', (('model', 4, 'wrong'),)), \
                    patch('huggingface_hub.hf_hub_download', side_effect=OSError('offline')) as fetch:
                with self.assertRaises(OSError):
                    await runtime._models(AsyncMock())
                target.write_bytes(b'1234')
                with self.assertRaisesRegex(RuntimeError, 'integridade'):
                    await runtime._models(AsyncMock())
                self.assertEqual(target.read_bytes(), b'1234')
                self.assertEqual(fetch.call_count, 1)


class TurboVulkanTests(unittest.IsolatedAsyncioTestCase):
    async def test_vulkan_loads_real_turbo_not_previous_base(self):
        runtime = sd._ZImageTurboPipeline()
        with patch.object(sd, '_ensure_sd_cli_binary', return_value=Path('sd-cli')), \
                patch('huggingface_hub.hf_hub_download', side_effect=lambda **kw: kw['filename']) as download:
            await runtime.load(sd.QWEN_IMAGE_TURBO_REPO, quality=sd.QWEN_IMAGE_2_FAST_AMD_QUALITY)
            self.assertEqual(runtime._resources.diffusion_model.name, sd.QWEN_IMAGE_TURBO_FILE)
            checkpoint = download.call_args_list[0].kwargs
            self.assertEqual(checkpoint['repo_id'], sd.QWEN_IMAGE_TURBO_REPO)
            self.assertEqual(checkpoint['revision'], sd.QWEN_IMAGE_TURBO_REVISION)

    async def test_vulkan_uses_official_eight_step_sigmas_and_cfg_one(self):
        runtime = sd._ZImageTurboPipeline()
        runtime._quality = sd.QWEN_IMAGE_2_FAST_AMD_QUALITY
        runtime._resources = sd._ZImageResources(Path('sd-cli'), Path(sd.QWEN_IMAGE_TURBO_FILE), Path('encoder'), Path('vae'))
        commands = []
        process = SimpleNamespace(returncode=0, stdout=None, stderr=None, wait=AsyncMock(return_value=0))
        async def execute(*args, **kwargs):
            commands.append(args)
            Path(args[args.index('-o') + 1]).write_bytes(b'png fixture')
            return process
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(sd, 'IMAGE_OUTPUT_DIR', Path(temporary)), \
                patch.object(sd, '_prepare_image_prompt', AsyncMock(return_value='A landscape')), \
                patch.object(sd, '_prepare_reference_images', AsyncMock(return_value=[])), \
                patch.object(sd, '_qwen_image_memory_args', return_value=[]), \
                patch.object(sd, '_supports_native_sage_attention', return_value=False), \
                patch.object(sd.asyncio, 'create_subprocess_exec', side_effect=execute):
            await runtime.generate('Landscape', resolution='1:1')
        command = commands[0]
        self.assertEqual(command[command.index('--sigmas') + 1], fast.SIGMAS)
        self.assertEqual(command[command.index('--steps') + 1], '8')
        self.assertEqual(command[command.index('--cfg-scale') + 1], '1')


if __name__ == '__main__':
    unittest.main()
