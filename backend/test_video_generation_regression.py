import ast
from pathlib import Path
import subprocess
import unittest
from typing import Optional
import asyncio
import io
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from fastapi import UploadFile

ROOT = Path(__file__).resolve().parents[1]


def h3_builder(source):
    tree = ast.parse(source)
    namespace = {"Optional": Optional}
    for item in tree.body:
        if isinstance(item, ast.Assign):
            try:
                value = ast.literal_eval(item.value)
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        namespace[target.id] = value
            except (ValueError, TypeError):
                pass
    align = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_align_video_dimension"
    )
    runtime = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "MiniMaxH3Runtime"
    )
    build = next(
        n
        for n in runtime.body
        if isinstance(n, ast.FunctionDef) and n.name == "_build_workflow"
    )
    build.decorator_list = []
    exec(
        compile(
            ast.Module(body=[align, build], type_ignores=[]), "h3_workflow", "exec"
        ),
        namespace,
    )
    return namespace["_build_workflow"]


class VideoGraphTests(unittest.TestCase):
    def test_h3_graphs_are_unchanged(self):
        path = "backend/neveai/routers/video_generation.py"
        old = h3_builder(
            subprocess.check_output(
                ["git", "show", "HEAD:" + path], cwd=ROOT, text=True, encoding="utf8"
            )
        )
        new = h3_builder((ROOT / path).read_text(encoding="utf8"))
        for width, height in [(864, 480), (1184, 672), (480, 864)]:
            for frames in [124, 196]:
                for refs in [
                    (None, None),
                    ("first.png", None),
                    ("first.png", "last.png"),
                ]:
                    for merged in [True, False]:
                        with self.subTest(
                            width=width,
                            height=height,
                            frames=frames,
                            refs=refs,
                            merged=merged,
                        ):
                            kwargs = dict(
                                last_image=refs[1],
                                width=width,
                                height=height,
                                frames=frames,
                                low_vram_lora=merged,
                            )
                            self.assertEqual(
                                old("Scene", 42, refs[0], **kwargs),
                                new("Scene", 42, refs[0], **kwargs),
                            )


class VideoHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree = ast.parse(
            (ROOT / "backend/neveai/utils/middleware.py").read_text(encoding="utf8")
        )
        function = next(
            n
            for n in tree.body
            if isinstance(n, ast.AsyncFunctionDef)
            and n.name == "chat_video_generation_handler"
        )

        class Imports(ast.NodeTransformer):
            def visit_Import(self, node):
                return None

            def visit_ImportFrom(self, node):
                return None

        function = Imports().visit(function)
        for arg in function.args.args:
            arg.annotation = None
        function.returns = None
        self.events = []
        self.runtime = SimpleNamespace(
            session_lock=asyncio.Lock(),
            prepare=AsyncMock(),
            generate=AsyncMock(
                return_value={"video": b"test-video", "filename": "test.mp4"}
            ),
            stop=AsyncMock(),
        )
        self.upload = Mock(return_value=SimpleNamespace(id="created-video"))
        self.release = Mock()
        self.references = []
        prepared = SimpleNamespace(
            width=640,
            height=480,
            path=SimpleNamespace(
                read_bytes=lambda: b"reference", unlink=lambda **kw: None
            ),
        )

        def validate(*args, references, max_images, **kwargs):
            if len(references) > max_images:
                raise ValueError("Too many images")

        namespace = dict(
            Optional=Optional,
            asyncio=asyncio,
            Path=Path,
            io=io,
            uuid4=uuid4,
            UploadFile=UploadFile,
            log=logging.getLogger("video-handler-test"),
            _collect_stable_diffusion_prompt=lambda *args: "Scene",
            _collect_stable_diffusion_image_references=lambda *args, **kwargs: self.references,
            _validate_media_attachments=validate,
            has_permission=lambda *args: True,
            _acquire_media_generation_slot=AsyncMock(),
            _release_media_generation_slot=self.release,
            video_canvas_dimensions=lambda resolution, aspect, size=None: size
            or (864, 480),
            model_manager=SimpleNamespace(standby=AsyncMock()),
            _prepare_init_image_sync=lambda *args: prepared,
            minimax_h3_runtime=self.runtime,
            upload_file_handler=self.upload,
        )
        exec(
            compile(
                ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                "real-video-handler",
                "exec",
            ),
            namespace,
        )
        self.handler = namespace[function.name]
        self.request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    config=SimpleNamespace(
                        ENABLE_VIDEO_GENERATION=True, USER_PERMISSIONS={}
                    )
                ),
                url_path_for=lambda *a, **kw: "/api/v1/files/created-video/content",
            )
        )
        self.user = SimpleNamespace(id="test-user")

    async def invoke(self, duration="5s"):
        async def emitter(event):
            self.events.append(event)

        self.metadata = {}
        return await self.handler(
            self.request,
            {"messages": []},
            {
                "__metadata__": self.metadata,
                "__event_emitter__": emitter,
                "__features__": {
                    "video_generation_duration": duration,
                },
            },
            self.user,
        )

    async def test_requests_use_minimax_with_original_frames(self):
        for duration, frames in [("5s", 124), ("8s", 196)]:
            for count in range(3):
                with self.subTest(duration=duration, references=count):
                    self.runtime.generate.reset_mock()
                    self.release.reset_mock()
                    self.references = ["first", "last"][:count]
                    await self.invoke(duration=duration)
                    kwargs = self.runtime.generate.await_args.kwargs
                    self.assertEqual(kwargs["frames"], frames)
                    self.assertEqual(kwargs["last_image"] is not None, count == 2)
                    self.assertEqual(
                        self.upload.call_args.kwargs["metadata"]["source"],
                        "minimax-h3-fl2va-w4a8",
                    )
                    self.assertTrue(self.metadata["skip_llm"])
                    self.assertTrue(any(e["type"] == "files" for e in self.events))
                    self.release.assert_called_once_with(True)

    async def test_failure_releases_worker_and_slot(self):
        self.runtime.generate.side_effect = RuntimeError("Test failure")
        await self.invoke()
        self.upload.assert_not_called()
        self.assertGreaterEqual(self.runtime.stop.await_count, 1)
        self.release.assert_called_once_with(True)
        self.assertTrue(
            any(e["type"] == "status" and e["data"].get("error") for e in self.events)
        )

    async def test_cancel_releases_worker_and_slot(self):
        self.runtime.generate.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.invoke()
        self.assertGreaterEqual(self.runtime.stop.await_count, 1)
        self.release.assert_called_once_with(True)

    async def test_too_many_references_never_start_worker(self):
        self.references = ["first", "last", "third"]
        await self.invoke()
        self.runtime.prepare.assert_not_awaited()
        self.runtime.generate.assert_not_awaited()
        self.release.assert_called_once_with(False)


if __name__ == "__main__":
    unittest.main()


