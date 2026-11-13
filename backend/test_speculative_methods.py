import tempfile
import unittest
from pathlib import Path

from gguf import GGUFWriter
from neveai.utils.speculative_decoding import supports_embedded_mtp, mark_mtp_unavailable, _has_mtp, _unavailable
from test_gpu_priority import manager_fixture


def write_model(path, layers):
    writer = GGUFWriter(str(path), 'qwen35')
    writer.add_uint32('qwen35.nextn_predict_layers', layers)
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()


class SpeculativeMethodsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / 'test.gguf'
        self.runtime = self.root / 'server.exe'
        self.runtime.write_bytes(b'runtime')
        _has_mtp.cache_clear()
        _unavailable.clear()
        self.manager, self.ns = manager_fixture(self.root)
        self.ns['MTP_UNSUPPORTED_MESSAGE'] = 'MTP unavailable'

    def test_detection_uses_metadata_and_invalidates_on_runtime_change(self):
        write_model(self.model, 1)
        self.assertTrue(supports_embedded_mtp(self.model, self.runtime))
        mark_mtp_unavailable(self.model, self.runtime)
        self.assertFalse(supports_embedded_mtp(self.model, self.runtime))
        self.runtime.write_bytes(b'updated runtime')
        self.assertTrue(supports_embedded_mtp(self.model, self.runtime))
        write_model(self.model, 0)
        self.assertFalse(supports_embedded_mtp(self.model, self.runtime))

    async def test_auto_selects_mtp_and_retains_auto_for_profile_matching(self):
        write_model(self.model, 1)
        result = await self.manager.load_model('test.gguf', n_ctx=4096, token_prediction='auto')
        self.assertEqual(self.manager._start_server.call_args.args[8], 'on')
        self.assertEqual(result['token_prediction'], 'auto')
        self.assertEqual(result['speculative_method'], 'mtp')
        await self.manager.load_model('test.gguf', n_ctx=4096, token_prediction='auto')
        self.assertEqual(self.manager._start_server.await_count, 1)

    async def test_auto_selects_ngram_without_embedded_head(self):
        write_model(self.model, 0)
        result = await self.manager.load_model('test.gguf', n_ctx=4096, token_prediction='auto')
        self.assertEqual(self.manager._start_server.call_args.args[7:9], ('high', 'off'))
        self.assertEqual(result['speculative_method'], 'ngram')

    async def test_auto_falls_back_without_changing_context(self):
        for error in ['MTP unavailable', 'out of memory']:
            with self.subTest(error=error):
                _unavailable.clear()
                self.manager._loaded.clear()
                self.manager._start_server.reset_mock()
                write_model(self.model, 1)
                self.manager._start_server.side_effect = [RuntimeError(error), None]
                result = await self.manager.load_model('test.gguf', n_ctx=4096, token_prediction='auto')
                self.assertEqual(result['n_ctx'], 4096)
                self.assertEqual(result['speculative_method'], 'ngram')
                self.assertEqual(self.manager._start_server.await_count, 2)
                self.assertEqual(self.manager._start_server.call_args_list[0].args[8], 'on')
                self.assertEqual(self.manager._start_server.call_args_list[1].args[7:9], ('high', 'off'))

    async def test_explicit_mtp_does_not_silently_change_method(self):
        write_model(self.model, 0)
        self.manager._start_server.side_effect = RuntimeError('MTP unavailable')
        with self.assertRaises(RuntimeError):
            await self.manager.load_model('test.gguf', n_ctx=4096, token_prediction='on')
        self.assertEqual(self.manager._start_server.await_count, 1)

    async def test_context_shift_masks_auto(self):
        write_model(self.model, 1)
        result = await self.manager.load_model('test.gguf', n_ctx=4096, token_prediction='auto', context_shift='on')
        self.assertEqual(result['token_prediction'], 'off')
        self.assertEqual(result['speculative_method'], 'off')

    async def test_standby_resume_retains_auto_and_its_effective_method(self):
        write_model(self.model, 1)
        await self.manager.load_model('test.gguf', n_ctx=4096, token_prediction='auto')
        async def unload(model_id):
            self.manager._loaded.pop(model_id)
        self.manager.unload_model = unload
        snapshot = await self.manager.standby()
        self.assertEqual(snapshot['models'][0]['token_prediction'], 'auto')
        await self.manager.resume(snapshot)
        self.assertEqual(self.manager._loaded['local/test'].token_prediction, 'auto')
        self.assertEqual(self.manager._loaded['local/test'].speculative_method, 'mtp')


if __name__ == '__main__':
    unittest.main()
