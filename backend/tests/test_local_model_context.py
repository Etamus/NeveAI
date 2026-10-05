import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from neveai.utils.local_model_context import (
    bounded_context, context_memory_margin, plan_auto_context, runtime_context,
)


class ContextPlannerTests(unittest.TestCase):
    def test_api_defaults_to_auto_and_rejects_negative_context(self):
        from neveai.routers.llamacpp import LoadModelRequest
        self.assertEqual(LoadModelRequest(filename="test.gguf").n_ctx, 0)
        self.assertEqual(LoadModelRequest(filename="test.gguf", n_ctx=65536).n_ctx, 65536)
        with self.assertRaises(ValueError):
            LoadModelRequest(filename="test.gguf", n_ctx=-1)

    def test_conservative_limit_and_rounding_never_expand_model_context(self):
        for value, expected in [(262144, 32768), (30000, 16384), (8192, 8192), (1500, 1024), (512, 512)]:
            self.assertEqual(bounded_context(value), expected)
        with self.assertRaises(ValueError):
            bounded_context(0)

    def test_margin_reserves_projector_and_prediction_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            projector = Path(directory) / "mmproj.gguf"
            projector.write_bytes(b"test")
            self.assertEqual(context_memory_margin(None, False), 2048)
            self.assertEqual(context_memory_margin(None, True), 3072)
            self.assertEqual(context_memory_margin(projector, True), 3585)

    def test_reads_runtime_properties_and_legacy_log_without_guessing(self):
        self.assertEqual(runtime_context({"default_generation_settings": {"n_ctx": 12288}}, ""), 12288)
        self.assertEqual(runtime_context({}, "n_ctx = 32768\nn_ctx_per_seq = 8192"), 8192)
        for props in [{}, {"default_generation_settings": {"n_ctx": 0}}, {"default_generation_settings": {"n_ctx": True}}]:
            with self.assertRaises(RuntimeError):
                runtime_context(props, "")

    def test_native_fit_handles_cpu_gpu_cache_device_and_explicit_layers(self):
        with patch.object(Path, "exists", return_value=True), patch("neveai.utils.local_model_context.subprocess.run") as run:
            run.return_value = Mock(returncode=0, stdout="-c 55000 -ngl 20\n", stderr="")
            args = (Path("runtime"), Path("model.gguf"))
            self.assertEqual(plan_auto_context(*args, -1, "q8_0", device="Vulkan0"), (32768, 20))
            command = run.call_args.args[0]
            self.assertIn("q8_0", command)
            self.assertIn("Vulkan0", command)
            self.assertEqual(plan_auto_context(*args, 0, "f16"), (32768, 0))
            self.assertEqual(plan_auto_context(*args, 12, "q4_0"), (32768, 12))

    def test_missing_failed_timed_out_or_invalid_preflight_uses_native_server_fit(self):
        args = (Path("runtime"), Path("model.gguf"), -1, "f16")
        with patch.object(Path, "exists", return_value=False):
            self.assertEqual(plan_auto_context(*args), (0, -1))
        for result in [Mock(returncode=1, stderr="failed"), Mock(returncode=0, stdout="not valid", stderr="")]:
            with patch.object(Path, "exists", return_value=True), patch("neveai.utils.local_model_context.subprocess.run", return_value=result):
                self.assertEqual(plan_auto_context(*args), (0, -1))
        with patch.object(Path, "exists", return_value=True), patch("neveai.utils.local_model_context.subprocess.run", side_effect=subprocess.TimeoutExpired("fit", 45)):
            self.assertEqual(plan_auto_context(*args), (0, -1))


class ContextLoadingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from neveai.routers import llamacpp
        self.router = llamacpp
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        (self.directory / "test.gguf").write_bytes(b"test")
        self.manager = llamacpp.LocalModelManager()
        self.manager._start_server = AsyncMock()
        self.manager._kill_server = AsyncMock()
        self.manager._cleanup_stale = Mock()
        self.manager._next_free_port = Mock(return_value=18099)
        self.manager._read_log_tail = Mock(return_value="")
        self.manager._is_process_alive = Mock(return_value=True)
        self.response = Mock()
        self.response.json.return_value = {"default_generation_settings": {"n_ctx": 16384}}
        client = Mock(get=AsyncMock(return_value=self.response))
        self.patchers = [patch.object(llamacpp, "MODELS_DIR", self.directory),
                         patch.object(llamacpp, "preferred_vulkan_device", return_value=None),
                         patch.object(llamacpp, "plan_auto_context", return_value=(32768, 25)),
                         patch.object(llamacpp, "_get_http_client", return_value=client)]
        self.mocks = [p.start() for p in self.patchers]

    async def asyncTearDown(self):
        for p in reversed(self.patchers):
            p.stop()
        self.temp.cleanup()

    async def test_auto_records_effective_context_and_offload_and_publishes_mode(self):
        result = await self.manager.load_model("test.gguf", n_ctx=0, mmproj_filename="")
        self.assertEqual(result["n_ctx"], 16384)
        self.assertEqual(result["n_gpu_layers"], 25)
        self.assertTrue(result["context_auto"])
        self.assertTrue(self.manager.scan_models()[0]["context_auto"])
        self.assertTrue(self.manager._start_server.call_args.kwargs["auto_context"])

    async def test_manual_context_never_uses_fit_or_changes_requested_size(self):
        result = await self.manager.load_model("test.gguf", n_ctx=65536, mmproj_filename="")
        self.assertEqual(result["n_ctx"], 65536)
        self.assertFalse(result["context_auto"])
        self.mocks[2].assert_not_called()

    async def test_native_fallback_is_capped_before_becoming_ready(self):
        self.mocks[2].return_value = (0, -1)
        self.response.json.side_effect = [{"default_generation_settings": {"n_ctx": 131072}}, {"default_generation_settings": {"n_ctx": 32768}}]
        result = await self.manager.load_model("test.gguf", n_ctx=0, mmproj_filename="")
        self.assertEqual(result["n_ctx"], 32768)
        self.assertEqual(self.manager._start_server.call_count, 2)
        self.manager._kill_server.assert_awaited_once()

    async def test_memory_failure_retries_a_smaller_auto_context(self):
        self.manager._start_server.side_effect = [RuntimeError("out of memory"), None]
        result = await self.manager.load_model("test.gguf", n_ctx=0, mmproj_filename="")
        self.assertEqual(result["n_ctx"], 16384)
        self.assertEqual(self.manager._start_server.call_args.args[2], 16384)

    async def test_mtp_allocation_failure_is_not_misreported_as_unsupported(self):
        self.manager._processes["local/test"] = Mock(poll=Mock(return_value=1))
        self.manager._read_log_tail.return_value = "creating MTP draft context: failed to allocate buffer: out of memory"
        with self.assertRaisesRegex(RuntimeError, "out of memory"):
            await self.manager._wait_for_server(18099, "local/test")

    async def test_manual_memory_and_nonmemory_errors_never_silently_change_context(self):
        for context, message in [(65536, "out of memory"), (0, "unsupported architecture")]:
            self.manager._start_server.reset_mock()
            self.manager._start_server.side_effect = RuntimeError(message)
            with self.assertRaises(RuntimeError):
                await self.manager.load_model("test.gguf", n_ctx=context, mmproj_filename="")
            self.assertEqual(self.manager._start_server.call_count, 1)

    async def test_unverifiable_context_cleans_up_instead_of_publishing_zero(self):
        self.response.json.return_value = {}
        with self.assertRaises(RuntimeError):
            await self.manager.load_model("test.gguf", n_ctx=0, mmproj_filename="")
        self.assertEqual(self.manager._loaded, {})
        self.manager._kill_server.assert_awaited_once()

    async def test_standby_and_resume_preserve_auto_mode_and_effective_context(self):
        await self.manager.load_model("test.gguf", n_ctx=0, mmproj_filename="")
        self.manager.unload_model = AsyncMock()
        snapshot = await self.manager.standby()
        self.assertTrue(snapshot["models"][0]["context_auto"])
        self.manager._loaded.clear()
        await self.manager.resume(snapshot)
        info = self.manager._loaded["local/test"]
        self.assertTrue(info.context_auto)
        self.assertEqual(info.n_ctx, 16384)


if __name__ == "__main__":
    unittest.main()
