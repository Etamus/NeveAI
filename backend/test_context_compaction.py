import asyncio
import ast
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

from neveai.utils.context_compaction import ContextCompactor

ROOT = Path(__file__).resolve().parent


class CompactionRoutingTests(unittest.TestCase):
    def test_opt_in_is_local_strict_boolean_and_cannot_leak_from_custom_params(self):
        tree = ast.parse((ROOT / 'neveai/utils/middleware.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'apply_params_to_form_data')
        scope = {'json': json, 'deep_update': lambda a, b: dict(a, **b)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'real-parameter-routing', 'exec'), scope)
        for owner in ['llamacpp', 'openai', 'ollama']:
            for value in [True, False, 'true', 1, None]:
                for custom in [None, {}, {'context_compaction': True}]:
                    with self.subTest(owner=owner, value=value, custom=custom):
                        result = scope['apply_params_to_form_data'](
                            {'params': {'context_compaction': value, 'custom_params': custom, 'temperature': .4}},
                            {'owned_by': owner})
                        if owner == 'llamacpp':
                            self.assertIs(result['context_compaction'], value is True)
                        else:
                            self.assertNotIn('context_compaction', result)
                        self.assertEqual(result['temperature'], .4)

    def test_unsafe_integration_and_continuation_gates(self):
        tree = ast.parse((ROOT / 'neveai/routers/llamacpp.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'generate_chat_completion')
        assignment = next(n for n in fn.body if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == 'compaction_unsafe' for t in n.targets))
        def unsafe(form=None, metadata=None, response_format=None):
            scope = dict(form_data=form or {}, metadata=metadata or {}, response_format=response_format)
            exec(compile(ast.Module(body=[assignment], type_ignores=[]), 'real-compaction-gate', 'exec'), scope)
            return bool(scope['compaction_unsafe'])
        self.assertFalse(unsafe())
        self.assertTrue(unsafe({'continue_response': True}))
        self.assertTrue(unsafe(metadata={'continue_response': True}))
        self.assertTrue(unsafe({'tools': [{'type': 'function'}]}))
        self.assertTrue(unsafe(response_format={'type': 'json_object'}))
        self.assertTrue(unsafe(metadata={'files': [{'id': 'attachment'}]}))
        self.assertTrue(unsafe(metadata={'tool_ids': ['tool']}))
        for feature in ['web_search', 'deep_search', 'file_generation', 'code_execution',
                        'stable_diffusion', 'video_generation', 'music_generation']:
            self.assertTrue(unsafe(metadata={'features': {feature: True}}))
            self.assertFalse(unsafe(metadata={'features': {feature: False}}))


class CompactionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = ContextCompactor()
        self.messages = [{"role": "system", "content": "Exact system instruction"}]
        for i in range(5):
            self.messages += [
                {"role": "user", "content": f"Keep literal instruction {i}: MAGENTA_873"},
                {"role": "assistant", "content": (f"Answer {i}. " * 700)},
            ]
        self.messages.append({"role": "user", "content": "Continue with all constraints"})
        self.summarize = AsyncMock(return_value="All constraints retained. MAGENTA_873. Price 37.")

    async def count(self, messages):
        return sum(len(m['content']) // 4 + 8 for m in messages)

    async def run_compact(self, **kwargs):
        return await self.engine.compact(kwargs.pop('messages', self.messages), context_window=8192,
            scope=kwargs.pop('scope', 'user:chat:model:session'), count=kwargs.pop('count', self.count),
            summarize=kwargs.pop('summarize', self.summarize))

    async def test_preserves_all_instructions_latest_answers_and_original(self):
        before = copy.deepcopy(self.messages)
        compacted = await self.run_compact()
        self.assertIsNot(compacted, self.messages)
        self.assertEqual(self.messages, before)
        self.assertEqual([m for m in compacted if m['role'] != 'assistant'],
                         [m for m in before if m['role'] != 'assistant'])
        self.assertEqual(compacted[-4:], before[-4:])
        self.assertEqual([m['role'] for m in compacted], [m['role'] for m in before])
        self.assertLess(await self.count(compacted), await self.count(before) * .6)

    async def test_cache_and_isolation(self):
        await self.run_compact()
        await self.run_compact()
        self.assertEqual(self.summarize.await_count, 1)
        await self.run_compact(scope='other-user:chat:model:session')
        self.assertEqual(self.summarize.await_count, 2)
        await self.run_compact(scope='user:chat:model:new-load')
        self.assertEqual(self.summarize.await_count, 3)

    async def test_short_histories_never_infer(self):
        await self.run_compact(count=AsyncMock(return_value=100))
        self.summarize.assert_not_awaited()
        await self.run_compact(messages=self.messages[-4:])
        self.summarize.assert_not_awaited()

    async def test_structured_multimodal_and_continue_are_untouched(self):
        for changed in [dict(role='tool', content='result'),
                        dict(role='user', content=[{'type': 'text', 'text': 'attachment'}]),
                        dict(role='assistant', content='call', tool_calls=[]),
                        dict(role='assistant', content='continue this')]:
            messages = self.messages + [changed]
            self.assertIs(await self.run_compact(messages=messages), messages)
        self.summarize.assert_not_awaited()

    async def test_failures_and_bad_summaries_fall_back(self):
        for summary in [None, '', ' ', '<think>hidden', '<details>reasoning']:
            self.assertIs(await self.run_compact(summarize=AsyncMock(return_value=summary)), self.messages)
        for error in [RuntimeError('unavailable'), TimeoutError('timeout')]:
            self.assertIs(await self.run_compact(summarize=AsyncMock(side_effect=error)), self.messages)
        self.assertIs(await self.run_compact(count=AsyncMock(side_effect=RuntimeError('unsupported template'))), self.messages)

    async def test_insufficient_saving_and_input_too_large(self):
        count = AsyncMock(side_effect=[7000, 1000, 6900])
        self.assertIs(await self.run_compact(count=count), self.messages)
        self.engine = ContextCompactor()
        summary = AsyncMock()
        self.assertIs(await self.run_compact(count=AsyncMock(side_effect=[8000, 8000]), summarize=summary), self.messages)
        summary.assert_not_awaited()

    async def test_cancellation_propagates(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.run_compact(summarize=AsyncMock(side_effect=asyncio.CancelledError()))

    async def test_complete_internal_reasoning_never_enters_summary(self):
        compacted = await self.run_compact(summarize=AsyncMock(return_value='<think>Internal only</think>Keep MAGENTA_873.'))
        self.assertNotIn('Internal only', str(compacted))
        self.assertIn('Keep MAGENTA_873.', str(compacted))

    async def test_cache_is_bounded_and_does_not_retain_transcripts(self):
        for i in range(40):
            await self.run_compact(scope=f'user:chat:{i}')
        self.assertEqual(len(self.engine._cache), 32)
        self.assertTrue(all(isinstance(value, str) for value in self.engine._cache.values()))
        self.assertNotIn('Answer 0.', str(self.engine._cache))


if __name__ == '__main__':
    unittest.main()
