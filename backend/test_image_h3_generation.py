"""Isolated MiniMax image graph, dimensions, lifecycle and routing regression tests."""
import asyncio
import ast
import base64
import io
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from uuid import uuid4
import unittest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import Request, UploadFile

from PIL import Image
from neveai.routers import image_h3_generation as h3


class H3ImageTests(unittest.IsolatedAsyncioTestCase):
    def test_canvas_sizes_are_patch_aligned_and_reference_aware(self):
        for ratio in ("1:1", "16:9", "9:16", "4:3", "3:4"):
            w, h = h3.canvas_size(ratio)
            self.assertEqual(w % 32, 0)
            self.assertEqual(h % 32, 0)
            self.assertLess(abs(w * h - 4 * 1024**2), 100000)
        self.assertGreater(h3.canvas_size("auto", (1920, 1080))[0], h3.canvas_size("auto", (1920, 1080))[1])

    def test_graph_uses_image_weights_six_steps_full_encoder_and_all_references(self):
        for count in (0, 1, 2, 10):
            refs = [f"{index}.png" for index in range(count)]
            graph = h3.NeveImage3Runtime.build_workflow("Edit imagem 1 using image 2", 2048, 2048, refs, 42)
            self.assertEqual(graph["1"]["inputs"]["unet_name"], h3.MODEL)
            self.assertEqual(graph["2"]["inputs"]["clip_name"], h3.ENCODER)
            self.assertEqual(graph["6"]["inputs"]["steps"], 6)
            self.assertEqual(graph["6"]["inputs"]["cfg"], 1)
            self.assertNotIn("LoRA", str(graph))
            self.assertNotIn("turbo_v4", str(graph))
            for index in range(1, count + 1):
                self.assertIn(f"images.image_{index}", graph["4"]["inputs"])
        with self.assertRaises(ValueError):
            h3.NeveImage3Runtime.build_workflow("x", 2048, 2048, ["x"] * 11, 42)

    def test_reference_prompt_keeps_existing_picture_labels_and_literal_text(self):
        self.assertEqual(h3.reference_prompt("Uma xicara azul", 0), "Uma xicara azul")
        self.assertTrue(h3.reference_prompt("Edit <Picture 1>. Keep <Picture 2>.", 2).startswith("Edit <Picture 1>. Keep <Picture 2>."))
        self.assertNotIn("<<Picture", h3.reference_prompt("Edit <Picture 1>. Keep <Picture 2>.", 2))
        self.assertIn("<Picture 2>", h3.reference_prompt("Use imagem 2", 2))
        self.assertIn('"imagem 2"', h3.reference_prompt('Write "imagem 2" on image 1', 2))
        self.assertIn("<Picture 1>", h3.reference_prompt('Write "imagem 2" on image 1', 2))

    def test_quality_does_not_fall_back_to_another_image_model(self):
        from neveai.routers.stable_diffusion import normalize_image_quality
        self.assertEqual(normalize_image_quality(h3.QUALITY), h3.QUALITY)
        self.assertEqual(normalize_image_quality("neve_image_2"), "qwen_image_2s")
        for old in ("qwen_image_2s", "qwen_image_2_1_official"):
            self.assertEqual(normalize_image_quality(old), old)

    async def test_cancellation_stops_worker_and_releases_request_lock(self):
        runtime = h3.NeveImage3Runtime()
        entered = asyncio.Event()
        async def install(progress):
            entered.set()
            await asyncio.sleep(100)
        with patch.object(runtime, "_install", side_effect=install), patch.object(runtime, "_stop", new_callable=AsyncMock) as stop:
            task = asyncio.create_task(runtime.run("x", "1:1", [], None, AsyncMock()))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            stop.assert_awaited_once()
        self.assertFalse(runtime._request_lock.locked())

    def test_initial_dimensions_match_the_generation_dimensions(self):
        from neveai.utils.image_progress import initial_image_dimensions
        raw = io.BytesIO()
        Image.new("RGB", (640, 960)).save(raw, "PNG")
        with patch("neveai.routers.stable_diffusion._read_image_reference_bytes", return_value=raw.getvalue()):
            self.assertEqual(initial_image_dimensions(h3.QUALITY, "auto", ["file"], None, (1, 1)), h3.canvas_size("auto", (640, 960)))
        self.assertEqual(initial_image_dimensions(h3.QUALITY, "16:9", [], None, (1, 1)), h3.canvas_size("16:9"))

    async def test_chat_routing_library_metadata_and_standby_restore(self):
        from neveai.utils.media_standby import media_model_standby
        from neveai.routers import stable_diffusion as sd
        from neveai.routers import llamacpp
        source = Path(__file__).parent / "neveai/utils/middleware.py"
        function = next(node for node in ast.parse(source.read_text(encoding="utf8")).body if isinstance(node, ast.AsyncFunctionDef) and node.name == "chat_stable_diffusion_handler")
        upload = Mock(return_value=SimpleNamespace(id="created-image"))
        release = Mock()
        namespace = dict(Request=Request, Optional=Optional, asyncio=asyncio, io=io, base64=base64, uuid4=uuid4,
                         UploadFile=UploadFile, log=logging.getLogger("image3-routing-test"),
                         media_model_standby=media_model_standby, upload_file_handler=upload,
                         _collect_stable_diffusion_prompt=lambda *a, **kw: "Uma caneca azul",
                         _collect_stable_diffusion_image_references=lambda *a, **kw: [],
                         _validate_media_attachments=lambda *a, **kw: None,
                         _acquire_media_generation_slot=AsyncMock(), _release_media_generation_slot=release)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "image3-real-chat-handler", "exec"), namespace)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=SimpleNamespace(
            STABLE_DIFFUSION_MODEL="default", STABLE_DIFFUSION_HF_TOKEN="", STABLE_DIFFUSION_WIDTH=1024,
            STABLE_DIFFUSION_HEIGHT=1024, STABLE_DIFFUSION_STEPS=8, STABLE_DIFFUSION_GUIDANCE_SCALE=1)),
            url_path_for=lambda *a, **kw: "/api/v1/files/created-image/content"))
        manager = SimpleNamespace(standby=AsyncMock(return_value={"models": ["old"]}), resume=AsyncMock(), get_loaded_model_id=lambda: None)
        uri = "data:image/png;base64," + base64.b64encode(b"image-bytes").decode()
        events = []
        async def emit(event):
            events.append(event)
        metadata = {}
        with patch.object(llamacpp, "model_manager", manager), patch.object(sd._sd_pipeline, "unload", new_callable=AsyncMock), patch.object(h3.neve_image_3_runtime, "run", new_callable=AsyncMock, return_value=uri) as run:
            await namespace[function.name](request, {"messages": []}, {"__metadata__": metadata, "__event_emitter__": emit,
                "__features__": {"stable_diffusion_quality": h3.QUALITY}}, SimpleNamespace(id="user"))
        run.assert_awaited_once()
        manager.standby.assert_awaited_once()
        manager.resume.assert_awaited_once()
        self.assertTrue(metadata["skip_llm"])
        self.assertEqual(upload.call_args.kwargs["metadata"]["source"], "neve-image-3")
        self.assertTrue(upload.call_args.kwargs["metadata"]["generated"])
        self.assertEqual(upload.call_args.kwargs["metadata"]["quality"], h3.QUALITY)
        self.assertTrue(any(e["type"] == "files" for e in events))
        self.assertTrue(any(e["type"] == "status" and e["data"].get("done") and not e["data"].get("error") for e in events))
        release.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
