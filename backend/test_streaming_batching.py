"""Run the real middleware producer via AST, without DB/application imports."""

import ast
import asyncio
import copy
from contextlib import suppress
import html
import json
from pathlib import Path
import re
import statistics
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
def load_nodes(relative_path, names, scope, constants=False):
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names:
            nodes.append(node)
        elif constants and isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id.startswith(
                ("DEFAULT_REASONING_", "DEFAULT_SOLUTION_", "REASONING_", "CHANNEL_CONTROL_", "STREAM_CONTROL_")
            ) for target in node.targets
        ):
            nodes.append(node)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), scope)
    return tree


class ReasoningStreamTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.emitter = AsyncMock()
        self.scope = dict(re=re, html=html, json=json, time=time, uuid4=uuid4,
                          log=Mock(), metadata={"params": {}}, request=Mock(), user=Mock(),
                          event_emitter=self.emitter, get_image_urls=lambda *args: [],
                          CHAT_RESPONSE_STREAM_DELTA_CHUNK_SIZE=1,
                          ENABLE_CHAT_RESPONSE_BASE64_IMAGE_URL_CONVERSION=False,
                          ENABLE_REALTIME_CHAT_SAVE=False, DETECT_REASONING_TAGS=True,
                          DETECT_CODE_INTERPRETER=False, discard_excess_source_reasoning=False,
                          tool_calls=[], generate_chat_completion=AsyncMock())
        tree = load_nodes("backend/neveai/utils/middleware.py", {
            "hide_partial_control_tokens", "output_id", "strip_reasoning_control_tokens",
            "strip_reasoning_text_artifacts", "is_reasoning_continuation",
            "has_reasoning_continuation", "reopen_reasoning_continuation",
            "should_hide_reasoning_output", "serialize_output",
        }, self.scope, constants=True)
        self.scope["reasoning_tags"] = self.scope["DEFAULT_REASONING_TAGS"]
        self.scope.update(asyncio=asyncio, suppress=suppress)
        load_nodes("backend/neveai/utils/streaming.py", {
            "run_sync_chat_operation", "stream_with_flush_ticks",
        }, self.scope)
        tag_handler = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "tag_output_handler")
        handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "stream_body_handler")
        factory = ast.parse("def make_handler(initial_output=None):\n    content = ''\n    usage = {}\n    output = initial_output if initial_output is not None else []\n").body[0]
        factory.body.extend([tag_handler, handler, ast.Return(value=ast.Tuple(elts=[ast.Name(id="stream_body_handler", ctx=ast.Load()), ast.Name(id="output", ctx=ast.Load())], ctx=ast.Load()))])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[factory], type_ignores=[])), "stream-test", "exec"), self.scope)

    async def run_stream(self, deltas, on_chunk=None, initial_output=None):
        async def body():
            for delta in deltas:
                yield "data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n\n"
                if on_chunk:
                    on_chunk()
            yield "data: [DONE]\n\n"
        handler, output = self.scope["make_handler"](copy.deepcopy(initial_output))
        response = SimpleNamespace(body_iterator=body(), background=None,
                                   headers={"X-Neve-Budgeted-Reasoning": "true"})
        await handler(response, {"messages": [], "reasoning_mode": "reasoning"})
        self.scope["log"].debug.assert_not_called()
        self.scope["generate_chat_completion"].assert_not_awaited()
        return output

    async def test_continuing_completed_reasoning_starts_a_new_block(self):
        old = {"type": "reasoning", "id": "old-reasoning", "status": "completed",
               "attributes": {"type": "reasoning_content"}, "started_at": time.time() - 60,
               "ended_at": time.time() - 55, "duration": 5,
               "content": [{"type": "output_text", "text": "Old thought"}]}
        output = await self.run_stream([
            {"reasoning_content": "New thought"}, {"content": "Visible continuation"},
        ], initial_output=[old])
        self.assertEqual([item["type"] for item in output], ["reasoning", "reasoning", "message"])
        self.assertEqual(output[0], old)
        self.assertEqual(output[1]["content"][0]["text"], "New thought")
        self.assertEqual(output[1]["status"], "completed")
        rendered = self.scope["serialize_output"](output)
        self.assertEqual(rendered.count('<details type="reasoning"'), 2)
        self.assertTrue(rendered.endswith("Visible continuation"))

    async def test_continuation_keeps_the_previous_answer_and_contains_raw_reasoning(self):
        old = {"type": "message", "id": "old-answer", "status": "completed", "role": "assistant",
               "content": [{"type": "output_text", "text": "Previous answer."}]}
        output = await self.run_stream([
            {"content": "<thi"}, {"content": "nk>New private thought"},
            {"content": "</think>Continued answer."},
        ], initial_output=[old])
        self.assertEqual([item["type"] for item in output], ["message", "reasoning", "message"])
        self.assertEqual(output[0]["content"][0]["text"], "Previous answer.")
        # The outer response handler releases an ambiguous short post-reasoning tail at EOF.
        output[-1].pop('_reasoning_boundary_pending', None)
        rendered = self.scope["serialize_output"](output)
        self.assertIn('New private thought', rendered.split('</details>')[0])
        self.assertNotIn('New private thought', rendered.split('</details>')[-1])
        self.assertTrue(rendered.endswith('Continued answer.'))

    async def test_short_answer_is_emitted_immediately_without_second_generation(self):
        frames = []
        output = await self.run_stream(
            [{"reasoning_content": "Consider the question."}, {"content": "42"}],
            lambda: frames.append([copy.deepcopy(call.args[0]) for call in self.emitter.await_args_list]),
        )
        self.assertIn("42", frames[1][-1]["data"]["content"])
        self.assertEqual([item["type"] for item in output], ["reasoning", "message"])
        self.assertEqual(output[1]["content"][0]["text"], "42")
        self.assertEqual(output[0]["status"], "completed")

    async def test_authoritative_answer_channel_does_not_reopen_reasoning(self):
        output = await self.run_stream([
            {"reasoning_content": "Consider the question."},
            {"content": "Analysis"}, {"content": " of the results: 42."},
        ])
        self.assertEqual(len(output), 2)
        self.assertEqual(output[0]["content"][0]["text"], "Consider the question.")
        self.assertEqual(output[0]["status"], "completed")
        self.assertEqual(output[1]["content"][0]["text"], "Analysis of the results: 42.")

    async def test_reasoning_only_stream_is_finalized(self):
        output = await self.run_stream([{"reasoning_content": "Thinking."}])
        self.assertEqual(output[0]["status"], "completed")
        self.assertGreaterEqual(output[0]["duration"], 0)

    async def test_raw_tag_stream_still_parses_without_second_generation(self):
        output = await self.run_stream([
            {"content": "<think>Consider this."},
            {"content": "</think>"}, {"content": "42"},
        ])
        self.assertEqual(output[0]["type"], "reasoning")
        self.assertEqual(output[0]["status"], "completed")
        self.assertEqual(output[1]["content"][0]["text"], "42")



class StreamingBatchTests(ReasoningStreamTests):
    def setUp(self):
        super().setUp()
        self.frames = []
        self.emitter.side_effect = lambda event: self.frames.append(copy.deepcopy(event))
        self.scope["request"].state.direct = False
        self.scope["metadata"].update(chat_id="test-chat", message_id="test-message")
        self.worker_threads = []
        self.saved = []

        def save(*args):
            self.worker_threads.append(threading.get_ident())
            self.saved.append(copy.deepcopy(args[-1]))

        self.scope["Chats"] = SimpleNamespace(
            upsert_message_to_chat_by_id_and_message_id=save,
            add_message_files_by_id_and_message_id=lambda *args: args[-1],
        )
        self.scope["normalize_usage"] = lambda usage: usage
        self.scope["_split_tool_calls"] = lambda calls: calls
        load_nodes("backend/neveai/utils/middleware.py", {
            "handle_responses_streaming_event", "deep_merge", "split_content_and_whitespace",
            "is_opening_code_block",
        }, self.scope)
        self.render = Mock(wraps=self.scope["serialize_output"])
        self.scope["serialize_output"] = self.render

    def contents(self):
        return [frame["data"]["content"] for frame in self.frames
                if frame.get("type") == "chat:completion" and "content" in frame.get("data", {})]

    async def consume_outer(self, body, message=None, messages=None):
        self.scope["Chats"].get_message_by_id_and_message_id = lambda *args: copy.deepcopy(message)
        self.scope["Chats"].get_chat_title_by_id = lambda *args: "Test"
        self.scope.update(
            form_data={"messages": messages or [], "model": "test"}, model={}, ctx={},
            get_last_user_message=lambda *args: "test",
            get_last_assistant_message=lambda messages: messages[-1]["content"],
            get_system_message=lambda *args: None,
            CHAT_RESPONSE_MAX_TOOL_CALL_RETRIES=0,
            publish_pending_generated_files=AsyncMock(), background_tasks_handler=AsyncMock(),
        )
        tree = ast.parse((ROOT / "backend/neveai/utils/middleware.py").read_text(encoding="utf-8"))
        handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                       and n.name == "response_handler")
        exec(compile(ast.fix_missing_locations(ast.Module(body=[handler], type_ignores=[])),
                     "outer-stream-test", "exec"), self.scope)
        await self.scope["response_handler"](SimpleNamespace(body_iterator=body, background=None), [])
        self.scope["log"].debug.assert_not_called()

    async def test_temporary_continuation_preserves_old_blocks_and_normalizes_new_reasoning(self):
        old_output = [
            {"type": "reasoning", "id": "old-r", "status": "completed", "duration": 3,
             "attributes": {"type": "reasoning_content"},
             "content": [{"type": "output_text", "text": "Old private thought"}]},
            {"type": "message", "id": "old-m", "status": "completed", "role": "assistant",
             "content": [{"type": "output_text", "text": "Old visible answer."}]},
        ]
        self.scope["metadata"].update(continue_response=True, continuation_output=copy.deepcopy(old_output))
        async def body():
            yield self.sse({"choices": [{"delta": {"reasoning_content": "New private thought"}}]})
            yield self.delta("New visible answer.")
        await self.consume_outer(body(), messages=[{"role": "assistant", "content": "Old visible answer."}])
        final = self.saved[-1]
        self.assertEqual(final["output"][:2], old_output)
        self.assertEqual([item["type"] for item in final["output"]], ["reasoning", "message", "reasoning", "message"])
        self.assertEqual(final["content"].count('<details type="reasoning"'), 2)
        self.assertIn('Old visible answer.', final["content"])
        self.assertNotIn('private thought', final["content"].split('</details>')[-1])

    async def test_legacy_temporary_continuation_keeps_existing_display_content(self):
        display = '<details type="reasoning" done="true">\n<summary>Thought</summary>\n&gt; Old thought\n</details>\nOld answer.'
        self.scope["metadata"].update(continue_response=True, continuation_content=display)
        async def body():
            yield self.delta(" More answer.")
        await self.consume_outer(body(), messages=[{"role": "assistant", "content": "Old answer."}])
        self.assertIn(display, self.saved[-1]["content"])
        self.assertIn('More answer.', self.saved[-1]["content"])

    async def test_responses_api_continuation_keeps_previous_output_and_uses_new_indices(self):
        old = {"type": "message", "id": "old-m", "status": "completed", "role": "assistant",
               "content": [{"type": "output_text", "text": "Old answer."}]}
        self.scope["metadata"].update(continue_response=True, continuation_output=[copy.deepcopy(old)])
        reason = {"type": "reasoning", "id": "new-r", "status": "completed",
                  "summary": [{"type": "summary_text", "text": "New private thought"}]}
        answer = {"type": "message", "id": "new-m", "status": "completed", "role": "assistant",
                  "content": [{"type": "output_text", "text": "New answer."}]}
        async def body():
            yield self.sse({"type": "response.output_item.added", "item": {
                **reason, "status": "in_progress", "summary": []}})
            yield self.sse({"type": "response.reasoning_summary_part.added", "output_index": 0,
                            "part": {"type": "summary_text", "text": ""}})
            yield self.sse({"type": "response.reasoning_summary_text.delta", "output_index": 0,
                            "summary_index": 0, "delta": "New private thought"})
            yield self.sse({"type": "response.output_item.done", "output_index": 0, "item": reason})
            yield self.sse({"type": "response.output_item.added", "item": {
                **answer, "status": "in_progress", "content": [{"type": "output_text", "text": ""}]}})
            yield self.sse({"type": "response.output_text.delta", "output_index": 1, "delta": "New answer."})
            yield self.sse({"type": "response.completed", "response": {"output": [reason, answer]}})
        await self.consume_outer(body(), messages=[{"role": "assistant", "content": "Old answer."}])
        self.assertEqual(self.saved[-1]["output"], [old, reason, answer])
        self.assertIn('Old answer.', self.saved[-1]["content"])
        self.assertIn('New private thought', self.saved[-1]["content"].split('</details>')[0])
        self.assertNotIn('New private thought', self.saved[-1]["content"].split('</details>')[-1])

    async def test_outer_final_state_is_saved_even_with_realtime_enabled(self):
        self.scope["ENABLE_REALTIME_CHAT_SAVE"] = True

        async def body():
            yield self.delta("a ")
            yield self.delta("b ")

        await self.consume_outer(body())
        self.assertEqual(self.frames[-1]["data"]["content"], "a b")
        self.assertTrue(self.frames[-1]["data"]["done"])
        self.assertEqual(self.saved[-1]["content"], "a b")
        self.assertEqual(self.saved[-1]["output"][0]["status"], "completed")

    async def test_outer_cancel_and_failure_save_partial_state_without_done(self):
        for realtime in (False, True):
            for exception in (asyncio.CancelledError(), RuntimeError("upstream")):
                self.scope["ENABLE_REALTIME_CHAT_SAVE"] = realtime
                self.frames.clear()
                self.saved.clear()

                async def body():
                    yield self.delta("a")
                    yield self.delta("b")
                    raise exception

                if isinstance(exception, asyncio.CancelledError):
                    await self.consume_outer(body())
                    self.assertEqual(self.frames[-1]["type"], "chat:tasks:cancel")
                else:
                    with self.assertRaises(RuntimeError):
                        await self.consume_outer(body())
                self.assertEqual(self.saved[-1]["content"], "ab")
                self.assertEqual(self.saved[-1]["output"][0]["status"], "in_progress")
                self.assertFalse(any(f.get("data", {}).get("done") for f in self.frames))

    async def consume(self, body):
        handler, output = self.scope["make_handler"]()
        await handler(SimpleNamespace(body_iterator=body, background=None), {"messages": []})
        self.scope["log"].debug.assert_not_called()
        return output

    @staticmethod
    def sse(data):
        return "data: " + json.dumps(data) + "\n\n"

    def delta(self, text):
        return self.sse({"choices": [{"delta": {"content": text}}]})

    async def test_cumulative_render_count_and_first_final_flush(self):
        consumed = []

        async def body():
            for index in range(257):
                yield self.delta("x" * 32)
                if index == 0:
                    self.assertEqual(self.contents(), ["x" * 32])
                consumed.append(index)

        await self.consume(body())
        self.assertEqual(len(consumed), 257)
        self.assertEqual(self.contents()[-1], "x" * (257 * 32))
        self.assertLess(self.render.call_count, 35)
        self.assertEqual(self.render.call_count, len(self.contents()))

    async def test_idle_upstream_flushes_without_waiting_for_next_token(self):
        flushed = asyncio.Event()

        def emit(frame):
            self.frames.append(copy.deepcopy(frame))
            if frame.get("data", {}).get("content") == "ab":
                flushed.set()

        self.emitter.side_effect = emit

        async def body():
            yield self.delta("a")
            yield self.delta("b")
            await asyncio.wait_for(flushed.wait(), 0.3)

        await self.consume(body())
        self.assertEqual(self.contents(), ["a", "ab"])

    async def test_usage_error_and_tool_calls_follow_pending_text(self):
        async def body():
            yield self.delta("a")
            yield self.delta("b")
            yield self.sse({"usage": {"total_tokens": 2}})
            yield self.delta("c")
            yield self.sse({"error": {"message": "failed"}})
            yield self.sse({"choices": [{"delta": {"tool_calls": [{
                "index": 0, "id": "call-1", "function": {"name": "search", "arguments": "{"},
            }]}}]})
            yield self.sse({"choices": [{"delta": {"tool_calls": [{
                "index": 0, "function": {"arguments": "}"},
            }]}}]})

        await self.consume(body())
        usage_index = next(i for i, f in enumerate(self.frames) if "usage" in f.get("data", {}))
        error_index = next(i for i, f in enumerate(self.frames) if "error" in f.get("data", {}))
        self.assertEqual(self.frames[usage_index - 1]["data"]["content"], "ab")
        self.assertEqual(self.frames[error_index - 1]["data"]["content"], "abc")
        self.assertEqual(self.scope["tool_calls"][0][0]["function"]["arguments"], "{}")

    async def test_realtime_save_is_batched_on_worker_and_contains_accumulated_text(self):
        self.scope["ENABLE_REALTIME_CHAT_SAVE"] = True
        await self.run_stream([{"content": "x"} for _ in range(65)])
        self.assertLess(len(self.saved), 12)
        self.assertEqual(self.saved[-1]["content"], "x" * 65)
        self.assertTrue(all(t != threading.get_ident() for t in self.worker_threads))
        self.assertTrue(all("choices" not in f.get("data", {}) for f in self.frames))

    async def test_upstream_failure_and_cancellation_flush_pending_state(self):
        for exception in (RuntimeError("upstream"), asyncio.CancelledError()):
            self.frames.clear()

            async def body():
                yield self.delta("a")
                yield self.delta("b")
                raise exception

            with self.assertRaises(type(exception)):
                await self.consume(body())
            self.assertEqual(self.contents()[-1], "ab")
            self.assertFalse(any(f.get("data", {}).get("done") for f in self.frames))

    async def test_responses_api_batches_text_but_preserves_structural_events(self):
        async def body():
            yield self.sse({"type": "response.output_item.added", "item": {
                "type": "message", "id": "msg-1", "role": "assistant", "status": "in_progress",
                "content": [{"type": "output_text", "text": ""}],
            }})
            for index in range(65):
                yield self.sse({"type": "response.output_text.delta", "delta": "x", "output_index": 0})
                if index == 0:
                    self.assertEqual(self.contents()[-1], "x")
            yield self.sse({"type": "response.completed", "response": {"usage": {"total_tokens": 65}}})

        await self.consume(body())
        self.assertEqual(self.contents()[-1], "x" * 65)
        self.assertLess(self.render.call_count, 15)
        self.assertTrue(self.frames[-1]["data"]["done"])
        self.assertEqual(self.frames[-1]["data"]["usage"], {"total_tokens": 65})

    async def test_cancelled_worker_is_joined_and_event_loop_keeps_running(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def operation():
            started.set()
            release.wait(1)
            finished.set()

        task = asyncio.create_task(self.scope["run_sync_chat_operation"](operation))
        while not started.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.sleep(0.005)
        self.assertFalse(task.done())
        task.cancel()
        await asyncio.sleep(0.005)
        self.assertFalse(task.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(finished.is_set())

    async def test_pending_files_and_background_sql_stay_on_workers(self):
        load_nodes("backend/neveai/utils/middleware.py", {
            "publish_pending_generated_files", "background_tasks_handler",
        }, self.scope)
        threads = []

        def db_result(value):
            def operation(*args):
                threads.append(threading.get_ident())
                return value
            return operation

        self.scope["Chats"].add_message_files_by_id_and_message_id = db_result([{"id": "file"}])
        self.scope["metadata"]["pending_generated_files"] = [{"id": "file"}]
        await self.scope["publish_pending_generated_files"](self.scope["metadata"], self.emitter)
        self.assertNotIn("pending_generated_files", self.scope["metadata"])
        self.scope["Chats"].get_messages_map_by_chat_id = db_result({})
        self.scope["Chats"].update_chat_title_by_id = db_result(None)
        self.scope["Chats"].get_chat_title_by_id = db_result("Existing title")
        self.scope.update(
            get_message_list=lambda *args: [
                {"content": "", "model": "test"}, {"content": "answer", "model": "test"},
            ],
            get_last_user_message=lambda *args: "question",
            _pasted_text_chat_title=lambda *args: "",
            generate_follow_ups=AsyncMock(return_value={"choices": [{"message": {
                "content": '{"follow_ups": ["Next?"]}',
            }}]}),
            TASKS=SimpleNamespace(FOLLOW_UP_GENERATION="followups", TITLE_GENERATION="title"),
        )
        await self.scope["background_tasks_handler"]({
            "request": self.scope["request"], "form_data": {}, "user": self.scope["user"],
            "metadata": self.scope["metadata"], "tasks": {"followups": True, "title": False},
            "event_emitter": self.emitter,
        })
        self.assertEqual(self.saved[-1], {"followUps": ["Next?"]})
        self.assertEqual(self.frames[-1], {"type": "chat:title", "data": "Existing title"})
        self.assertTrue(all(t != threading.get_ident() for t in threads + self.worker_threads))

    async def test_first_content_is_emitted_before_slow_realtime_write(self):
        self.scope["ENABLE_REALTIME_CHAT_SAVE"] = True
        started = threading.Event()
        release = threading.Event()

        def save(*args):
            started.set()
            release.wait(1)

        self.scope["Chats"].upsert_message_to_chat_by_id_and_message_id = save

        async def body():
            yield self.delta("first")

        task = asyncio.create_task(self.consume(body()))
        try:
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(0.001)
            self.assertTrue(started.is_set())
            self.assertEqual(self.contents(), ["first"])
            self.assertFalse(task.done())
        finally:
            release.set()
            await task

    async def test_code_interpreter_break_flushes_and_closes_upstream(self):
        self.scope["DETECT_CODE_INTERPRETER"] = True
        self.scope["DEFAULT_CODE_INTERPRETER_TAGS"] = [("<code_interpreter>", "</code_interpreter>")]
        closed = []

        async def body():
            try:
                yield self.delta('<code_interpreter type="code">print(42)')
                yield self.delta("</code_interpreter>")
                self.fail("upstream was consumed beyond interpreter boundary")
            finally:
                closed.append(True)

        output = await self.consume(body())
        self.assertEqual(closed, [True])
        self.assertEqual(output[-1]["type"], "neveai:code_interpreter")
        self.assertIn("print(42)", self.contents()[-1])

    async def test_empty_stream_and_bytes_done_marker(self):
        async def empty():
            yield b"data: [DONE]\n\n"

        await self.consume(empty())
        self.assertEqual(self.render.call_count, 0)
        self.assertEqual(self.frames, [])

    async def test_task_cancellation_closes_waiting_source_and_saves_partial_state(self):
        waiting = asyncio.Event()
        closed = []

        async def body():
            try:
                yield self.delta("a")
                yield self.delta("b")
                waiting.set()
                await asyncio.Event().wait()
            finally:
                closed.append(True)

        task = asyncio.create_task(self.consume_outer(body()))
        await asyncio.wait_for(waiting.wait(), 1)
        task.cancel()
        await task
        self.assertEqual(closed, [True])
        self.assertEqual(self.saved[-1]["content"], "ab")
        self.assertEqual(self.frames[-1]["type"], "chat:tasks:cancel")

    async def test_no_think_preserves_hidden_reasoning_and_visible_answer(self):
        self.scope["metadata"]["params"]["no_think"] = True
        output = await self.run_stream([
            {"reasoning_content": "private thought"}, {"reasoning_content": " continues"},
            {"content": "visible answer"},
        ])
        self.assertEqual(output[0]["content"][0]["text"], "private thought continues")
        self.assertEqual(self.contents()[-1], "visible answer")
        self.assertFalse(any("private" in content for content in self.contents()))

    async def test_responses_tool_argument_deltas_remain_immediate(self):
        async def body():
            yield self.sse({"type": "response.output_item.added", "item": {
                "type": "function_call", "id": "fc-1", "call_id": "call-1",
                "name": "search", "arguments": "", "status": "in_progress",
            }})
            for fragment, expected in (("{", "{"), ('"q":"x"}', '{"q":"x"}')):
                yield self.sse({"type": "response.function_call_arguments.delta", "delta": fragment})
                self.assertEqual(self.frames[-1]["data"]["output"][0]["arguments"], expected)

        await self.consume(body())

    def test_streaming_and_post_response_helpers_have_no_direct_chat_sql_calls(self):
        tree = ast.parse((ROOT / "backend/neveai/utils/middleware.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef) and node.name in {
                "streaming_chat_response_handler", "background_tasks_handler", "publish_pending_generated_files",
            }:
                calls = [call.lineno for call in ast.walk(node) if isinstance(call, ast.Call)
                         and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                         and call.func.value.id == "Chats"]
                self.assertEqual(calls, [], node.name)


async def benchmark():
    """Compare the same extracted producer with batching vs a per-event reference."""
    results = {}
    for mode in ("per_event_reference", "batched"):
        samples = []
        for _ in range(3):
            case = StreamingBatchTests()
            case.setUp()
            if mode == "per_event_reference":
                tree = ast.parse((ROOT / "backend/neveai/utils/middleware.py").read_text(encoding="utf-8"))
                handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                               and n.name == "stream_body_handler")
                for node in ast.walk(handler):
                    if isinstance(node, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "delta_chunk_size" for t in node.targets
                    ):
                        node.value = ast.Constant(value=1)
                tag = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                           and n.name == "tag_output_handler")
                factory = ast.parse("def make_handler():\n    content = ''\n    usage = {}\n    output = []\n").body[0]
                factory.body.extend([tag, handler, ast.Return(value=ast.Tuple(elts=[
                    ast.Name(id="stream_body_handler", ctx=ast.Load()), ast.Name(id="output", ctx=ast.Load()),
                ], ctx=ast.Load()))])
                exec(compile(ast.fix_missing_locations(ast.Module(body=[factory], type_ignores=[])),
                             "benchmark-reference", "exec"), case.scope)
            render_seconds = 0
            json_seconds = 0
            event_json_chars = 0

            def timed_render(*args, **kwargs):
                nonlocal render_seconds
                started = time.perf_counter()
                result = case.render(*args, **kwargs)
                render_seconds += time.perf_counter() - started
                return result

            def timed_emit(event):
                nonlocal json_seconds, event_json_chars
                started = time.perf_counter()
                encoded = json.dumps(event)
                json_seconds += time.perf_counter() - started
                event_json_chars += len(encoded)
                case.frames.append(copy.deepcopy(event))

            case.scope["serialize_output"] = timed_render
            case.emitter.side_effect = timed_emit
            started = time.perf_counter()
            await case.run_stream([{"content": "x" * 32} for _ in range(2048)])
            elapsed = (time.perf_counter() - started) * 1000
            samples.append({
                "producer_ms": elapsed,
                "serialize_output_ms": render_seconds * 1000,
                "event_json_ms": json_seconds * 1000,
                "serialize_calls": case.render.call_count,
                "event_json_chars": event_json_chars,
                "cumulative_content_chars": sum(map(len, case.contents())),
            })
            assert case.contents()[-1] == "x" * 65536
        results[mode] = {
            **{key: round(statistics.median(sample[key] for sample in samples), 3)
               for key in samples[0]},
            "final_chars": len(case.contents()[-1]),
            "samples": [{key: round(value, 3) for key, value in sample.items()}
                        for sample in samples],
        }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    if "--benchmark" in sys.argv:
        asyncio.run(benchmark())
    else:
        unittest.main()
