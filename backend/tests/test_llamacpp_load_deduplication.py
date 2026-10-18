import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from neveai.routers.llamacpp import LocalModelManager


class LocalLoadDeduplicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.model_dir = Path(self.directory.name)
        (self.model_dir / "test.gguf").touch()
        self.manager = LocalModelManager()
        self.manager._next_free_port = Mock(return_value=9999)

        async def start(*args, **kwargs):
            await asyncio.sleep(0.01)
            self.manager._processes["local/test"] = Mock(poll=Mock(return_value=None))

        async def stop(model_id):
            self.manager._processes.pop(model_id, None)

        self.manager._start_server = AsyncMock(side_effect=start)
        self.manager._kill_server = AsyncMock(side_effect=stop)
        patcher = patch("neveai.routers.llamacpp.MODELS_DIR", self.model_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_concurrent_identical_loads_start_one_server(self):
        results = await asyncio.gather(*[
            self.manager.load_model("test.gguf", n_ctx=8192) for _ in range(5)
        ])
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(self.manager._start_server.await_count, 1)
        self.manager._kill_server.assert_not_awaited()

    async def test_changed_profile_still_reloads(self):
        await self.manager.load_model("test.gguf", n_ctx=8192)
        result = await self.manager.load_model("test.gguf", n_ctx=4096, cache_type="q8_0")
        self.assertEqual(result["n_ctx"], 4096)
        self.assertEqual(result["cache_type"], "q8_0")
        self.assertEqual(self.manager._start_server.await_count, 2)
        self.manager._kill_server.assert_awaited_once()

    async def test_normalized_acceleration_profiles_do_not_restart(self):
        await self.manager.load_model("test.gguf", n_ctx=8192, speculative_decoding="low")
        await self.manager.load_model("test.gguf", n_ctx=8192, speculative_decoding="high")
        self.assertEqual(self.manager._start_server.await_count, 1)
        await self.manager.load_model("test.gguf", n_ctx=8192, context_shift="on", token_prediction="on")
        await self.manager.load_model("test.gguf", n_ctx=8192, context_shift="on", token_prediction="off")
        self.assertEqual(self.manager._start_server.await_count, 2)

    async def test_dead_process_is_not_reused(self):
        await self.manager.load_model("test.gguf", n_ctx=8192)
        self.manager._processes["local/test"].poll.return_value = 1
        await self.manager.load_model("test.gguf", n_ctx=8192)
        self.assertEqual(self.manager._start_server.await_count, 2)

    async def test_failed_start_can_be_retried(self):
        start = self.manager._start_server.side_effect
        self.manager._start_server.side_effect = RuntimeError("test startup failure")
        with self.assertRaises(RuntimeError):
            await self.manager.load_model("test.gguf", n_ctx=8192)
        self.manager._start_server.side_effect = start
        result = await self.manager.load_model("test.gguf", n_ctx=8192)
        self.assertEqual(result["status"], "loaded")

    async def test_automatic_context_reuses_the_resolved_profile(self):
        with patch("neveai.routers.llamacpp.plan_auto_context", return_value=(8192, -1)), \
             patch("neveai.routers.llamacpp.runtime_context", return_value=8192), \
             patch("neveai.routers.llamacpp._get_http_client") as client:
            response = Mock()
            response.json.return_value = {}
            client.return_value.get = AsyncMock(return_value=response)
            results = await asyncio.gather(*[
                self.manager.load_model("test.gguf", n_ctx=0) for _ in range(3)
            ])
        self.assertTrue(all(result["context_auto"] for result in results))
        self.assertEqual(self.manager._start_server.await_count, 1)


if __name__ == "__main__":
    unittest.main()
