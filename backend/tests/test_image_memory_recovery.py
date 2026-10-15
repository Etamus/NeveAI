import asyncio
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

from neveai.routers import image_fast_generation as fast
from neveai.routers import image_quality_generation as quality
from neveai.routers import stable_diffusion as sd
from neveai.utils.image_memory import ImageGenerationError, cpu_image_requested, cpu_image_size, is_image_memory_error, worker_error, monotonic_progress


class MemoryClassificationTests(unittest.TestCase):
    def test_explicit_cuda_disable_uses_cpu_without_disabling_amd(self):
        for mask in ('', '-1'):
            with patch.dict('os.environ', {'CUDA_VISIBLE_DEVICES': mask}):
                self.assertTrue(cpu_image_requested('cuda12'))
                self.assertTrue(cpu_image_requested('cpu'))
                self.assertFalse(cpu_image_requested('vulkan'))
    def test_cpu_canvas_is_bounded_without_upscaling(self):
        self.assertEqual(cpu_image_size(1152, 1152), (512, 512))
        self.assertEqual(cpu_image_size(128, 128), (128, 128))
        for width, height in [(1536, 864), (704, 1216), (7680, 4320)]:
            fitted = cpu_image_size(width, height)
            self.assertLessEqual(max(fitted), 512)
            self.assertTrue(all(side % 32 == 0 for side in fitted))
    def test_only_known_memory_errors_trigger_recovery(self):
        for error in [MemoryError(), 'CUDA out of memory', 'torch.OutOfMemoryError',
                      OSError(12, 'allocation unavailable'),
                      'std::bad_alloc', 'DefaultCPUAllocator: cannot allocate memory',
                      'VK ErrorOutOfDeviceMemory', 'CUDA_ERROR_OUT_OF_MEMORY',
                      'paging file is too small', 'CUBLAS_STATUS_ALLOC_FAILED']:
            self.assertTrue(is_image_memory_error(error), str(error))
        for error in ['invalid node', 'permission denied', 'download failed',
                      'CUDA illegal memory access', 'device lost', 'timeout', 'invalid image']:
            self.assertFalse(is_image_memory_error(error), error)

    def test_worker_errors_do_not_classify_an_echoed_prompt(self):
        status = {'status_str': 'error', 'messages': [['execution_error', {
            'exception_type': 'ValueError', 'exception_message': 'invalid shape',
            'current_inputs': {'prompt': 'out of memory'},
        }]]}
        self.assertFalse(is_image_memory_error(worker_error('image', status)))
        status['messages'][0][1]['exception_message'] = 'invalid prompt: CUDA out of memory'
        self.assertFalse(is_image_memory_error(worker_error('image', status)))
        self.assertFalse(is_image_memory_error(ImageGenerationError('echoed prompt: out of memory')))
        status['messages'][0][1].update(exception_type='torch.OutOfMemoryError', exception_message='CUDA out of memory')
        self.assertTrue(is_image_memory_error(worker_error('image', status)))


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_cpu_install_uses_cpu_wheels_and_no_cuda_assertion(self):
        runtime = fast.NeveImage2SRuntime()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            comfy = root / 'ComfyUI'
            comfy.mkdir()
            (comfy / 'main.py').touch()
            nodes = root / 'nodes'
            (nodes / 'ComfyUI-GGUF').mkdir(parents=True)
            (nodes / 'ComfyUI-GGUF/.neve-revision').write_text(fast.GGUF_COMMIT)
            python = root / 'python.exe'
            python.touch()
            with patch.object(type(runtime), 'is_installed', new_callable=PropertyMock, return_value=False), \
                    patch.object(fast, 'IMAGE_ROOT', root), patch.object(fast, 'COMFY_DIR', comfy), \
                    patch.object(fast, 'CUSTOM_NODES_DIR', nodes), patch.object(fast, 'MARKER', root / 'ready'), \
                    patch.object(fast, '_python', return_value=python), \
                    patch.object(runtime, '_command', new_callable=AsyncMock) as command, \
                    patch.object(fast.asyncio, 'create_subprocess_exec', return_value=SimpleNamespace(wait=AsyncMock(return_value=0))):
                await runtime._install(AsyncMock(), cpu_mode=True)
                commands = [call.args[0] for call in command.await_args_list]
                self.assertTrue(any('https://download.pytorch.org/whl/cpu' in cmd for cmd in commands))
                self.assertFalse(any('CUDA indisponivel' in str(cmd) for cmd in commands))
    async def test_image2_falls_back_once_to_gguf_and_preserves_seed_and_request(self):
        runtime = fast.NeveImage2SRuntime()
        calls = []
        async def attempt(*args, **kwargs):
            calls.append((args, kwargs))
            await args[4](45 if len(calls) == 1 else 12)
            if len(calls) == 1:
                raise RuntimeError('CUDA out of memory')
            return 'image'
        updates = []
        async def progress(value): updates.append(value)
        with patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'), \
                patch.object(runtime, '_run_once', side_effect=attempt):
            self.assertEqual(await runtime.run('Edit', '1:1', ['a', 'b'], 'user', progress), 'image')
        self.assertFalse(calls[0][1]['gguf'])
        self.assertTrue(calls[1][1]['gguf'])
        self.assertFalse(calls[1][1]['cpu_mode'])
        self.assertEqual(calls[0][1]['seed'], calls[1][1]['seed'])
        self.assertEqual(calls[0][0][:4], calls[1][0][:4])
        self.assertEqual(updates, [45, 45])

    async def test_both_comfy_runtimes_have_a_bounded_cpu_last_attempt(self):
        for runtime in [fast.NeveImage2SRuntime(), quality.NeveImage21Runtime()]:
            with self.subTest(runtime=type(runtime).__name__), \
                    patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'), \
                    patch.object(runtime, '_run_once', side_effect=[RuntimeError('CUDA out of memory'),
                        RuntimeError('out of memory'), 'cpu image']) as attempt:
                self.assertEqual(await runtime.run('Edit', '1:1', [], None, AsyncMock()), 'cpu image')
                self.assertEqual(attempt.await_count, 3)
                self.assertTrue(attempt.call_args.kwargs['cpu_mode'])

    async def test_cpu_only_starts_directly_in_gguf_cpu_mode(self):
        for runtime in [fast.NeveImage2SRuntime(), quality.NeveImage21Runtime()]:
            with self.subTest(runtime=type(runtime).__name__), \
                    patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cpu'), \
                    patch.object(runtime, '_run_once', return_value='cpu') as attempt:
                self.assertEqual(await runtime.run('Create', '1:1', [], None, AsyncMock()), 'cpu')
                self.assertEqual(attempt.await_count, 1)
                self.assertTrue(attempt.call_args.kwargs['cpu_mode'])
                self.assertTrue(attempt.call_args.kwargs.get('gguf', attempt.call_args.kwargs.get('force_gguf')))

    async def test_non_memory_errors_cancellation_and_exhaustion_propagate(self):
        for runtime in [fast.NeveImage2SRuntime(), quality.NeveImage21Runtime()]:
            for error in [ValueError('bad input'), asyncio.CancelledError(), RuntimeError('out of memory')]:
                with self.subTest(runtime=type(runtime).__name__, error=type(error).__name__), \
                        patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'), \
                        patch.object(runtime, '_run_once', side_effect=error) as attempt:
                    with self.assertRaises(type(error)):
                        await runtime.run('Edit', '1:1', [], None, AsyncMock())
                    self.assertEqual(attempt.await_count, 3 if is_image_memory_error(error) else 1)

    async def test_mageflow_recovery_and_state_are_isolated(self):
        runtime = sd._ZImageTurboPipeline()
        plans = []
        async def attempt(*args, **kwargs):
            plans.append((runtime._force_lightweight, runtime._force_cpu, runtime._recovery_seed))
            if len(plans) < 3: raise RuntimeError('out of memory')
            return 'cpu'
        with patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'), \
                patch.object(runtime, '_run_once', side_effect=attempt), \
                patch.object(runtime, 'unload', new_callable=AsyncMock):
            self.assertEqual(await runtime.run(sd.ZIMAGE_REPO, None, 'neve_image_2',
                                             prompt='Edit', init_image_reference='image'), 'cpu')
        self.assertEqual([p[:2] for p in plans], [(False, False), (True, False), (True, True)])
        self.assertEqual(len(set(p[2] for p in plans)), 1)
        self.assertFalse(runtime._force_cpu)
        self.assertIsNone(runtime._recovery_seed)

    async def test_cpu_planner_and_worker_commands_disable_gpu(self):
        runtime = quality.NeveImage21Runtime()
        runtime._cpu_mode = True
        self.assertIn('--cpu', runtime._comfy_command())
        self.assertEqual(runtime._pe_file(), quality.PE_LOW_VRAM_FILE)
        turbo = fast.NeveImage2SRuntime()
        turbo._cpu_mode = True
        self.assertIn('--cpu', turbo._comfy_command())

    async def test_cpu_edit_planner_disables_language_and_vision_gpu_offload(self):
        runtime = quality.NeveImage21Runtime()
        runtime._cpu_mode = True
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / 'llama-server.exe'
            binary.touch()
            (root / quality.PE_SYSTEM_FILE).write_text('rewrite faithfully')
            response = SimpleNamespace(raise_for_status=lambda: None,
                json=lambda: {'choices': [{'message': {'content': '{"rewritten_prompt":"Keep the original face"}'}}]})
            client = SimpleNamespace(post=AsyncMock(return_value=response))
            with patch('neveai.routers.llamacpp.LLAMACPP_SERVER_BIN', binary), \
                    patch.object(runtime, '_pe_directory', return_value=root), \
                    patch.object(runtime, '_start', return_value='http://isolated') as start, \
                    patch.object(runtime, '_stop', new_callable=AsyncMock), \
                    patch.object(quality.httpx, 'AsyncClient') as factory:
                factory.return_value.__aenter__.return_value = client
                self.assertEqual(await runtime._plan_edit('Edit', [b'fixture'], AsyncMock()), 'Keep the original face')
            command = start.call_args.args[0]
            self.assertEqual(command[command.index('--n-gpu-layers') + 1], '0')
            self.assertIn('--no-mmproj-offload', command)
            self.assertIn(quality.PE_LOW_VRAM_FILE, command[command.index('--model') + 1])

    async def test_recovery_serializes_requests_without_leaking_plans(self):
        runtime = quality.NeveImage21Runtime()
        events = []
        async def attempt(prompt, *args, **kwargs):
            events.append(prompt)
            await asyncio.sleep(.01)
            if prompt == 'first' and events.count(prompt) == 1:
                raise RuntimeError('out of memory')
            return prompt
        with patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'), \
                patch.object(runtime, '_run_once', side_effect=attempt):
            results = await asyncio.gather(runtime.run('first', '1:1', [], None, AsyncMock()),
                                           runtime.run('second', '1:1', [], None, AsyncMock()))
        self.assertEqual(results, ['first', 'second'])
        self.assertEqual(events, ['first', 'first', 'second'])
        self.assertIsNone(runtime._retry_prompt)


class MageflowLightTests(unittest.TestCase):
    def test_gguf_fallback_does_not_upscale_every_auxiliary_to_a_full_canvas(self):
        runtime = quality.NeveImage21Runtime()
        for count in range(4, 11):
            sizes = [runtime._reference_size(2048, 1536, quality.MODEL_FILE, index, count)
                     for index in range(count)]
            self.assertLessEqual(sum(w * h for w, h in sizes), 2.6 * 1024**2)
        runtime._cpu_mode = runtime._memory_saver = True
        self.assertLessEqual(max(runtime._reference_size(8192, 2048, quality.MODEL_FILE, 0, 10)), 512)

    def test_memory_boundaries_and_reference_budget(self):
        for memory, expected in [(None, True), (4096, True), (8191, True), (8192, False), (16384, False)]:
            with self.subTest(memory=memory), patch.object(sd, '_detected_gpu_vram_mib', return_value=memory):
                self.assertEqual(sd._use_lightweight_mageflow('neve_image_2', True), expected)
                self.assertFalse(sd._use_lightweight_mageflow('neve_image_2', False))
                self.assertFalse(sd._use_lightweight_mageflow('qwen_image_2s', True))
        pipeline = sd._ZImageTurboPipeline()
        with patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'), \
                patch.object(sd, '_detected_gpu_vram_mib', return_value=8192):
            flags = pipeline._mageflow_memory_args()
            self.assertEqual(flags[flags.index('--backend') + 1], 'te=cpu,vae=cpu,diffusion=cuda0')
            self.assertIn('--vae-tiling', flags)
            self.assertIn('--offload-to-cpu', flags)


if __name__ == '__main__': unittest.main()
