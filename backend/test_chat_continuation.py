"""Exercise the real continuation metadata/context branches without inference or a database."""
import ast
import copy
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ContinuationContextTests(unittest.TestCase):
    def reconstruct(self, continuing=False, temporary=False):
        source = ast.parse((ROOT / 'backend/neveai/utils/middleware.py').read_text(encoding='utf-8'))
        function = next(n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'process_chat_payload')
        assignment = next(n for n in function.body if isinstance(n, ast.Assign) and
                          any(isinstance(t, ast.Name) and t.id == 'context_message_id' for t in n.targets))
        branch = next(n for n in function.body if isinstance(n, ast.If) and
                      'context_message_id' in ast.unparse(n.test))
        metadata = {'message_id': 'answer', 'parent_message_id': 'question', 'continue_response': continuing}
        calls = []
        user = {'id': 'question', 'role': 'user', 'content': 'Tell a story'}
        assistant = {'id': 'answer', 'role': 'assistant', 'content': 'The story so far'}
        def load(chat, target):
            calls.append((chat, target))
            return copy.deepcopy([user, assistant] if target == 'answer' else [user])
        scope = dict(metadata=metadata, chat_id='local:fixture' if temporary else 'saved-chat',
                     parent_message_id='question', form_data={'messages': [user, assistant]},
                     load_messages_from_db=load, _get_file_generation_message_scope=lambda messages: ([], []),
                     get_system_message=lambda messages: None)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[assignment, branch], type_ignores=[])),
                     'continuation-context', 'exec'), scope)
        return scope, calls

    def test_continuation_includes_the_assistant_without_changing_its_parent(self):
        scope, calls = self.reconstruct(True)
        self.assertEqual(calls, [('saved-chat', 'answer')])
        self.assertEqual(scope['form_data']['messages'][-1]['role'], 'assistant')
        self.assertEqual(scope['metadata']['parent_message_id'], 'question')

    def test_normal_send_and_regeneration_still_end_at_the_user(self):
        scope, calls = self.reconstruct(False)
        self.assertEqual(calls, [('saved-chat', 'question')])
        self.assertEqual(scope['form_data']['messages'][-1]['role'], 'user')

    def test_temporary_continuation_retains_the_submitted_context(self):
        scope, calls = self.reconstruct(True, True)
        self.assertEqual(calls, [])
        self.assertEqual(scope['form_data']['messages'][-1]['id'], 'answer')

    def test_continuation_flag_is_consumed_as_metadata_not_forwarded_to_provider(self):
        tree = ast.parse((ROOT / 'backend/neveai/main.py').read_text(encoding='utf-8'))
        expression = next(value for node in ast.walk(tree) if isinstance(node, ast.Dict)
                          for key, value in zip(node.keys, node.values)
                          if isinstance(key, ast.Constant) and key.value == 'continue_response')
        for value, expected in [(True, True), (False, False), ('true', False), (None, False)]:
            data = {'continue_response': value, 'model': 'unchanged'}
            result = eval(compile(ast.Expression(body=expression), 'continuation-metadata', 'eval'), {'form_data': data})
            self.assertIs(result, expected)
            self.assertEqual(data, {'model': 'unchanged'})

    def test_temporary_chat_retains_structured_output_before_provider_conversion(self):
        tree = ast.parse((ROOT / 'backend/neveai/utils/middleware.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'process_chat_payload')
        branch = next(n for n in function.body if isinstance(n, ast.If) and
                      ast.unparse(n.test) == "metadata.get('continue_response')")
        output = [{'type': 'reasoning', 'status': 'completed'}, {'type': 'message', 'status': 'completed'}]
        for continuing in (False, True):
            scope = {'metadata': {'continue_response': continuing},
                     'form_data': {'messages': [{'role': 'assistant', 'output': output}]}}
            exec(compile(ast.fix_missing_locations(ast.Module(body=[branch], type_ignores=[])),
                         'continuation-output', 'exec'), scope)
            self.assertEqual(scope['metadata'].get('continuation_output'), output if continuing else None)

    def test_completed_prefill_gets_a_request_only_continuation_turn(self):
        tree = ast.parse((ROOT / 'backend/neveai/utils/middleware.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'process_chat_payload')
        branch = next(n for n in function.body if isinstance(n, ast.If) and
                      "Continue your previous response" in ast.unparse(n))
        for continuing in (False, True):
            original = [{'role': 'assistant', 'content': 'The complete answer.'}]
            scope = {'metadata': {'continue_response': continuing}, 'form_data': {'messages': copy.deepcopy(original)}}
            exec(compile(ast.fix_missing_locations(ast.Module(body=[branch], type_ignores=[])), 'continue-turn', 'exec'), scope)
            messages = scope['form_data']['messages']
            self.assertEqual(messages[:1], original)
            self.assertEqual(len(messages), 2 if continuing else 1)
            if continuing:
                self.assertEqual(messages[-1]['role'], 'user')
                self.assertIn('without repeating', messages[-1]['content'])


if __name__ == '__main__':
    unittest.main()
