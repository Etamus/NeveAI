"""Restored Video 1.5: direct prompts and only diffusion differs from Video 1."""
import ast
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from test_video_vdn_generation import ROOT, execute, vdn_namespace


def quality_namespace(cache):
    h3 = vdn_namespace(cache)['h3']
    namespace = dict(h3=h3, asyncio=asyncio)
    path = ROOT / 'backend/neveai/routers/video_quality_generation.py'
    nodes = [node for node in ast.parse(path.read_text(encoding='utf8')).body
             if not isinstance(node, (ast.Import, ast.ImportFrom))]
    execute(nodes, namespace)
    namespace['MODEL_SIZE'] = 2048
    return namespace


def populate(ns):
    for path in ns['video15_runtime']._model_paths():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x' * (ns['MODEL_SIZE'] if path == ns['MODEL_PATH'] else 1025))


class VideoQualityTests(unittest.IsolatedAsyncioTestCase):
    def test_only_diffusion_changes_and_direct_prompts_audio_references_survive(self):
        ns = quality_namespace(Path('test-cache'))
        base, quality = ns['h3'].MiniMaxH3Runtime, ns['NeveVideo15Runtime']
        prompt = 'Original request with "literal words" and accents: caf\u00e9.'
        for width, height in ((864,480),(1184,672),(480,864)):
            for frames in (124,196):
                for references in ((None,None),('first.png',None),(None,'last.png'),('first.png','last.png')):
                    for merged in (False,True):
                        with self.subTest(size=(width,height),frames=frames,refs=references,merged=merged):
                            args=(prompt,12345,*references,width,height,frames,merged)
                            original,graph=base._build_workflow(*args),quality._build_workflow(*args)
                            self.assertEqual(set(graph),set(original))
                            self.assertEqual({k for k in graph if graph[k]!=original[k]},{'6'})
                            self.assertEqual(graph['4']['inputs']['prompt'],prompt)
                            self.assertEqual(graph['4']['inputs']['clip'],['2',0])
                            self.assertEqual(graph['6']['inputs']['unet_name'],ns['DIFFUSION_MODEL'])
                            self.assertEqual(base._build_workflow(*args),original)

        self.assertNotIn('generate',quality.__dict__)
        self.assertNotIn('_start_server',quality.__dict__)
        self.assertFalse(hasattr(quality,'_compile_prompt'))

    def test_readiness_only_needs_original_assets_and_w6(self):
        with tempfile.TemporaryDirectory() as directory:
            ns=quality_namespace(Path(directory));populate(ns)
            runtime=ns['video15_runtime']
            self.assertTrue(runtime.models_ready)
            self.assertEqual(set(runtime._model_paths()),set(ns['h3'].MiniMaxH3Runtime._model_paths())|{ns['MODEL_PATH']})
            ns['MODEL_PATH'].write_bytes(b'partial')
            self.assertFalse(runtime.models_ready)

    async def test_pinned_download_and_cached_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            ns=quality_namespace(Path(directory));runtime=ns['video15_runtime']
            async def download(command):
                ast.parse(command[-1])
                self.assertIn(ns['MODEL_REVISION'],command[-1])
                self.assertNotIn('32b',command[-1])
                self.assertNotIn('8b_int8',command[-1])
                ns['MODEL_PATH'].parent.mkdir(parents=True,exist_ok=True)
                ns['MODEL_PATH'].write_bytes(b'x'*ns['MODEL_SIZE'])
            runtime._run_command=AsyncMock(side_effect=download)
            await runtime.prepare(AsyncMock())
            runtime._run_command.assert_awaited_once()
            runtime._run_command.reset_mock()
            await runtime.prepare(AsyncMock())
            runtime._run_command.assert_not_awaited()

    async def test_incomplete_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ns=quality_namespace(Path(directory));runtime=ns['video15_runtime']
            runtime._run_command=AsyncMock()
            with self.assertRaisesRegex(RuntimeError,'download.*nao foi concluido'):
                await runtime.prepare(AsyncMock())

    async def test_cancelled_download_releases_child_and_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            ns=quality_namespace(Path(directory));runtime=ns['video15_runtime']
            entered,released=asyncio.Event(),asyncio.Event()
            async def download(_):
                entered.set()
                try: await asyncio.Event().wait()
                finally: released.set()
            runtime._run_command=download
            task=asyncio.create_task(runtime.prepare(AsyncMock()))
            await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertTrue(released.is_set())
            self.assertFalse(runtime._runtime_lock.locked())

    def test_runtime_locks_and_process_state_are_isolated(self):
        ns=quality_namespace(Path('test-cache'))
        fast,quality=ns['h3'].MiniMaxH3Runtime(),ns['video15_runtime']
        self.assertIsNot(fast.session_lock,quality.session_lock)
        fast._process=object()
        self.assertIsNone(quality._process)


if __name__=='__main__': unittest.main()
