import ast
import asyncio
import json
import logging
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Optional
import unittest
from unittest.mock import AsyncMock

import httpx


def load_manager():
    path = Path(__file__).parent / 'neveai/routers/llamacpp.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'LocalModelManager')
    methods = [node for node in original.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {'__init__', 'unload_model', '_stream_proxy'}]
    cls = ast.ClassDef(name=original.name, bases=[], keywords=[], body=methods, decorator_list=[])
    info = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == '_LoadedModelInfo')
    ns = dict(asyncio=asyncio, httpx=httpx, json=json, time=time, Optional=Optional,
              log=logging.getLogger(__name__), _normalize_llamacpp_error_message=lambda value: value,
              _normalize_context_shift=lambda value: value, _normalize_token_prediction=lambda value: value,
              _normalize_speculative_decoding=lambda value: value)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[info, cls], type_ignores=[])), str(path), 'exec'), ns)
    manager = ns['LocalModelManager']()
    manager._loaded['local/test'] = ns['_LoadedModelInfo']('local/test', 'test.gguf', -1, 8192, 100)
    manager._kill_server = AsyncMock()
    return manager


class Response:
    def __init__(self, action=None, failure=None, status=200):
        self.action, self.failure, self.status_code = action, failure, status

    async def aread(self):
        return b'upstream error'

    async def aiter_lines(self):
        yield 'data: ' + json.dumps({'choices': [{'delta': {'content': 'Already generated'}, 'finish_reason': None}]})
        if self.action:
            await self.action()
        if self.failure is not None:
            raise self.failure
        yield 'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}], 'usage': {'completion_tokens': 2}})
        yield 'data: [DONE]'


class Client:
    def __init__(self, response, on_enter=None):
        self.response, self.on_enter = response, on_enter

    def stream(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        if self.on_enter:
            await self.on_enter()
        return self.response

    async def __aexit__(self, *args):
        return False


async def consume(manager, response, on_enter=None):
    raw = [chunk async for chunk in manager._stream_proxy(Client(response, on_enter), {}, 'local/test')]
    events = [json.loads(chunk[6:]) for chunk in raw if chunk.startswith('data: ') and chunk.strip() != 'data: [DONE]']
    content = ''.join(choice['delta'].get('content', '') for event in events for choice in event['choices'])
    return raw, events, content


class StreamUnloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_unload_preserves_generated_text_and_finishes_without_error_marker(self):
        manager = load_manager()
        raw, events, content = await consume(manager, Response(lambda: manager.unload_model('local/test'), httpx.ReadError('')))
        self.assertEqual(content, 'Already generated')
        self.assertEqual(events[-1]['choices'][0]['finish_reason'], 'stop')
        self.assertEqual(raw[-1], 'data: [DONE]\n\n')
        self.assertNotIn('local/test', manager._loaded)

    async def test_immediate_reload_does_not_change_the_old_stream_cancellation(self):
        manager = load_manager()
        async def reload():
            await manager.unload_model('local/test')
            manager._loaded['local/test'] = SimpleNamespace(n_ctx=16384, unload_requested=False)
        _, _, content = await consume(manager, Response(reload, httpx.ReadError('connection closed')))
        self.assertEqual(content, 'Already generated')
        self.assertFalse(manager._loaded['local/test'].unload_requested)

    async def test_unexpected_connection_failure_still_reports_error(self):
        manager = load_manager()
        _, _, content = await consume(manager, Response(failure=httpx.ReadError('broken connection')))
        self.assertIn('[Error: broken connection]', content)

    async def test_unexpected_empty_error_is_not_globally_hidden(self):
        _, _, content = await consume(load_manager(), Response(failure=httpx.ReadError('')))
        self.assertIn('[Error: ]', content)

    async def test_process_crash_is_not_treated_as_manual_unload(self):
        manager = load_manager()
        async def crash():
            manager._loaded.pop('local/test')
        _, _, content = await consume(manager, Response(crash, httpx.ReadError('crashed')))
        self.assertIn('[Error: crashed]', content)

    async def test_http_failure_after_manual_unload_is_empty(self):
        manager = load_manager()
        raw, events, content = await consume(manager, Response(status=503), lambda: manager.unload_model('local/test'))
        self.assertEqual(content, '')
        self.assertEqual(events[-1]['choices'][0]['delta'], {})
        self.assertEqual(raw[-1], 'data: [DONE]\n\n')

    async def test_http_failure_without_unload_is_preserved(self):
        _, _, content = await consume(load_manager(), Response(status=503))
        self.assertIn('upstream error', content)

    async def test_normal_stream_preserves_usage_and_model(self):
        raw, events, content = await consume(load_manager(), Response())
        self.assertEqual(content, 'Already generated')
        self.assertEqual(events[-1]['usage']['context_window'], 8192)
        self.assertEqual(events[-1]['model'], 'local/test')
        self.assertEqual(raw.count('data: [DONE]\n\n'), 1)

    async def test_unload_flag_is_set_before_closing_the_connection(self):
        manager = load_manager()
        info = manager._loaded['local/test']
        async def kill(model_id):
            self.assertTrue(info.unload_requested)
        manager._kill_server = kill
        self.assertFalse(info.unload_requested)
        self.assertNotIn('unload_requested', info.load_result())
        await manager.unload_model('local/test')


if __name__ == '__main__':
    unittest.main()
