import json
import unittest
from unittest.mock import patch

from test_stream_unload import load_manager, Client
from neveai.utils.response import normalize_usage


class MetricsResponse:
    status_code = 200

    async def aiter_lines(self):
        for index in range(101):
            yield 'data: ' + json.dumps({
                'choices': [{'delta': {'content': str(index) + ','}, 'finish_reason': None}],
                'timings': {'prompt_n': 100, 'predicted_n': index + 1, 'predicted_per_second': 50},
            })
        yield 'data: ' + json.dumps({
            'choices': [{'delta': {}, 'finish_reason': 'stop'}],
            'timings': {'prompt_n': 100, 'predicted_n': 101, 'predicted_per_second': 49},
            'usage': {'prompt_tokens': 100, 'completion_tokens': 101, 'total_tokens': 201},
        })
        yield 'data: [DONE]'


class LiveUsageTests(unittest.IsolatedAsyncioTestCase):
    async def test_samples_metrics_without_dropping_or_changing_text(self):
        manager = load_manager()
        with patch('time.monotonic', side_effect=[i * .01 for i in range(102)]):
            chunks = [x async for x in manager._stream_proxy(Client(MetricsResponse()), {}, 'local/test')]
        events = [json.loads(x[6:]) for x in chunks if '[DONE]' not in x]
        measured = [x for x in events if 'timings' in x]
        self.assertGreaterEqual(len(measured), 4)
        self.assertLessEqual(len(measured), 6)
        self.assertEqual(''.join(x['choices'][0]['delta'].get('content', '') for x in events), ''.join(str(i)+',' for i in range(101)))
        self.assertEqual(measured[0]['timings']['predicted_n'], 1)
        self.assertEqual(events[-1]['usage']['total_tokens'], 201)
        self.assertEqual(events[-1]['usage']['context_window'], 8192)
        self.assertEqual(events[-1]['timings']['predicted_per_second'], 49)
        self.assertEqual(chunks[-1], 'data: [DONE]\n\n')

    def test_normalizes_openai_and_native_counts(self):
        for value in [dict(prompt_tokens=100,completion_tokens=20),dict(prompt_n=100,predicted_n=20),dict(input_tokens=100,output_tokens=20)]:
            self.assertEqual(normalize_usage(value)['total_tokens'], 120)

    def test_native_speed_and_context_survive_normalization(self):
        value = normalize_usage(dict(prompt_n=100,predicted_n=20,predicted_per_second=49.5,context_window=8192))
        self.assertEqual(value['tokens_per_second'], 49.5)
        self.assertEqual(value['context_window'], 8192)

    def test_native_cache_counts_towards_context_but_not_generation_speed(self):
        value = normalize_usage(dict(cache_n=8811, prompt_n=4565, predicted_n=3008, predicted_per_second=98, context_window=16384))
        self.assertEqual(value['input_tokens'], 13376)
        self.assertEqual(value['output_tokens'], 3008)
        self.assertEqual(value['total_tokens'], 16384)
        self.assertEqual(value['tokens_per_second'], 98)
        self.assertEqual(normalize_usage(value), value)

    def test_never_double_counts_cache_in_standard_usage(self):
        for data in [dict(prompt_tokens=13376,completion_tokens=3008),dict(input_tokens=13376,output_tokens=3008)]:
            with self.subTest(data=data):
                value=normalize_usage({**data,'cache_n':8811,'prompt_n':4565,'predicted_n':3008})
                self.assertEqual(value['total_tokens'],16384)

    def test_string_and_invalid_counts_are_safe(self):
        self.assertEqual(normalize_usage(dict(cache_n='8811',prompt_n='4565',predicted_n='3008'))['total_tokens'],16384)
        for cached in [-1,float('nan'),'invalid',None]:
            self.assertEqual(normalize_usage(dict(cache_n=cached,prompt_n=27,predicted_n=39))['total_tokens'],66)


if __name__ == '__main__':
    unittest.main()
