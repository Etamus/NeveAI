import ast
import asyncio
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Optional
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from neveai.utils import local_model_context as context


def manager_fixture(root):
    path=Path(__file__).parent/'neveai/routers/llamacpp.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LocalModelManager')
    names={'__init__','load_model','standby','resume','_start_server'}
    methods=[n for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    info=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='_LoadedModelInfo')
    ns=dict(asyncio=asyncio,logging=logging,time=time,Optional=Optional,Path=Path,os=os,sys=sys,httpx=httpx,subprocess=subprocess,
            log=logging.getLogger(__name__),MODELS_DIR=root,MMPROJ_DIR=root,LLAMACPP_SERVER_DIR=root,LLAMACPP_SERVER_BIN=root/'server.exe',LLAMACPP_HOST='127.0.0.1',
            _normalize_context_shift=lambda x:x,_normalize_token_prediction=lambda x:x,_normalize_speculative_decoding=lambda x:x,
            preferred_vulkan_device=lambda x:None,plan_auto_context=Mock(return_value=(8192,-1)),require_gpu_device=Mock(),
            AUTO_CONTEXT_CAP=context.AUTO_CONTEXT_CAP,bounded_context=context.bounded_context,is_memory_failure=context.is_memory_failure,
            runtime_context=context.runtime_context,context_memory_margin=context.context_memory_margin,
            _get_http_client=lambda port:SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'default_generation_settings':{'n_ctx':8192}}))),
            _speculative_decoding_args=lambda x:[],_token_prediction_args=lambda x:[])
    compiled=ast.Module(body=[info,ast.ClassDef(name='LocalModelManager',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])
    exec(compile(ast.fix_missing_locations(compiled),str(path),'exec'),ns)
    manager=ns['LocalModelManager']()
    manager._cleanup_stale=Mock();manager.auto_detect_mmproj=lambda filename:None
    manager._is_process_alive=lambda model:True;manager._next_free_port=lambda:8285
    manager._kill_server=AsyncMock();manager._read_log_tail=lambda model:''
    manager._start_server=AsyncMock()
    return manager,ns


class PriorityLoadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'test.gguf').write_bytes(b'test')
        self.manager,self.ns=manager_fixture(self.root)

    def tearDown(self):self.temp.cleanup()

    async def test_default_is_unchanged_and_does_not_probe_gpu(self):
        result=await self.manager.load_model('test.gguf',n_ctx=4096)
        self.assertFalse(result['prioritize_gpu']);self.ns['require_gpu_device'].assert_not_called()
        self.assertFalse(self.manager._start_server.call_args.kwargs['prioritize_gpu'])

    async def test_cpu_load_remains_available_when_disabled(self):
        result=await self.manager.load_model('test.gguf',n_gpu_layers=0,n_ctx=4096)
        self.assertEqual(result['n_gpu_layers'],0)
        self.ns['require_gpu_device'].assert_not_called()

    async def test_non_memory_errors_do_not_trigger_context_retries(self):
        self.manager._start_server.side_effect=RuntimeError('invalid model tensor')
        with self.assertRaisesRegex(RuntimeError,'invalid model tensor'):
            await self.manager.load_model('test.gguf',n_ctx=0,prioritize_gpu=True)
        self.assertEqual(self.manager._start_server.await_count,1)

    async def test_exhausted_automatic_memory_retries_never_fall_back_to_cpu(self):
        self.manager._start_server.side_effect=RuntimeError('out of memory')
        with self.assertRaisesRegex(RuntimeError,'contexto automatico minimo'):
            await self.manager.load_model('test.gguf',n_ctx=0,prioritize_gpu=True)
        self.assertEqual([call.args[2] for call in self.manager._start_server.call_args_list],[8192,4096,2048])
        self.assertTrue(all(call.kwargs['prioritize_gpu'] for call in self.manager._start_server.call_args_list))
        self.assertNotIn('local/test',self.manager._loaded)

    async def test_priority_preserves_manual_context_and_cache(self):
        result=await self.manager.load_model('test.gguf',n_gpu_layers=0,n_ctx=16384,cache_type='q8_0',prioritize_gpu=True)
        self.assertEqual((result['n_gpu_layers'],result['n_ctx'],result['cache_type']),(-1,16384,'q8_0'))
        self.assertTrue(result['prioritize_gpu']);self.ns['plan_auto_context'].assert_not_called()

    async def test_automatic_retries_context_without_dropping_layers(self):
        self.manager._start_server.side_effect=[RuntimeError('out of memory'),None]
        result=await self.manager.load_model('test.gguf',n_ctx=0,prioritize_gpu=True)
        self.ns['plan_auto_context'].assert_called_once()
        self.assertTrue(self.ns['plan_auto_context'].call_args.kwargs['prioritize_gpu'])
        calls=self.manager._start_server.call_args_list
        self.assertEqual([c.args[2] for c in calls],[8192,4096])
        self.assertTrue(all(c.args[1]==-1 and c.kwargs['prioritize_gpu'] for c in calls))
        self.assertTrue(result['context_auto'])

    async def test_manual_oom_does_not_change_context_or_cache(self):
        self.manager._start_server.side_effect=RuntimeError('failed to alloc')
        with self.assertRaisesRegex(RuntimeError,'Reduza o contexto'):
            await self.manager.load_model('test.gguf',n_ctx=32768,cache_type='f16',prioritize_gpu=True)
        self.assertEqual(self.manager._start_server.await_count,1)
        self.assertNotIn('local/test',self.manager._loaded)

    async def test_no_gpu_does_not_unload_any_existing_model(self):
        self.ns['require_gpu_device'].side_effect=RuntimeError('No GPU')
        self.manager._loaded['other']=SimpleNamespace()
        with self.assertRaisesRegex(RuntimeError,'No GPU'):
            await self.manager.load_model('test.gguf',prioritize_gpu=True)
        self.manager._kill_server.assert_not_awaited();self.manager._start_server.assert_not_awaited()

    async def test_toggle_change_requires_reload_but_same_profile_does_not(self):
        await self.manager.load_model('test.gguf',n_ctx=4096)
        await self.manager.load_model('test.gguf',n_ctx=4096)
        self.assertEqual(self.manager._start_server.await_count,1)
        await self.manager.load_model('test.gguf',n_ctx=4096,prioritize_gpu=True)
        self.assertEqual(self.manager._start_server.await_count,2)
        await self.manager.load_model('test.gguf',n_ctx=4096,prioritize_gpu=True)
        self.assertEqual(self.manager._start_server.await_count,2)

    async def test_standby_and_resume_preserve_priority(self):
        await self.manager.load_model('test.gguf',n_ctx=4096,prioritize_gpu=True)
        async def unload(model):self.manager._loaded.pop(model)
        self.manager.unload_model=unload
        snapshot=await self.manager.standby()
        self.assertTrue(snapshot['models'][0]['prioritize_gpu'])
        await self.manager.resume(snapshot)
        self.assertTrue(self.manager._loaded['local/test'].prioritize_gpu)

    async def test_server_command_enforces_all_without_changing_manual_context(self):
        self.ns['LLAMACPP_SERVER_BIN'].write_bytes(b'fake')
        self.manager._get_log_path=lambda model:self.root/'runtime.log'
        self.manager._wait_for_server=AsyncMock()
        start=self.ns['LocalModelManager']._start_server
        with patch.object(subprocess,'Popen',return_value=Mock()) as popen:
            await start(self.manager,self.root/'test.gguf',-1,16384,None,8285,'local/test',prioritize_gpu=True)
        args=popen.call_args.args[0]
        self.assertEqual(args[args.index('--n-gpu-layers')+1],'all')
        self.assertEqual(args[args.index('--ctx-size')+1],'16384')
        self.assertEqual(args[args.index('--fit')+1],'off')


class ContextPriorityTests(unittest.TestCase):
    def test_fitter_never_replaces_full_gpu_with_fitted_cpu_layers(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'llama-fit-params.exe').touch()
            with patch.object(context.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='-c 9472 -ngl -2',stderr='')) as run:
                self.assertEqual(context.plan_auto_context(root,root/'model.gguf',-1,'f16',prioritize_gpu=True),(8192,-1))
            args=run.call_args.args[0]
            self.assertEqual(args[args.index('--n-gpu-layers')+1],'all')
            self.assertEqual(args[args.index('--fit-target')+1],'1024')

    def test_legacy_fitting_preserves_existing_margin_and_partial_offload(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'llama-fit-params.exe').touch()
            with patch.object(context.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='-c 2048 -ngl 62',stderr='')) as run:
                self.assertEqual(context.plan_auto_context(root,root/'model.gguf',-1,'f16'),(2048,62))
            args=run.call_args.args[0];self.assertEqual(args[args.index('--fit-target')+1],'2048')

    def test_missing_fitter_uses_full_gpu_context_retries_not_native_layer_fitting(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            self.assertEqual(context.plan_auto_context(root,root/'model.gguf',-1,'f16',prioritize_gpu=True),(32768,-1))
            self.assertEqual(context.plan_auto_context(root,root/'model.gguf',-1,'f16'),(0,-1))

    def test_device_detection_rejects_cpu_and_accepts_cuda_vulkan_and_metal(self):
        for value,accepted in [('Available devices:\n',False),(' CPU: test',False),(' CUDA0: NVIDIA',True),(' Vulkan1: AMD',True),(' Metal: Apple',True)]:
            with patch.object(context.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=value)):
                if accepted:context.require_gpu_device(Path('.'))
                else:
                    with self.assertRaisesRegex(RuntimeError,'GPU compativel'):context.require_gpu_device(Path('.'))


if __name__=='__main__':unittest.main()
