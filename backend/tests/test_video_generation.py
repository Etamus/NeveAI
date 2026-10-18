import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from neveai.routers.video_generation import (
    DIFFUSION_MODEL,
    VIDEO_MAX_PIXELS,
    VIDEO_OUTPUT_CRF,
    VIDEO_RESOLUTION_DIMENSIONS,
    MiniMaxH3Runtime,
    video_canvas_dimensions,
    _use_merged_video_lora,
    _video_lora_out_of_memory,
    _VideoLoRAMemoryError,
)
from neveai.utils.middleware import _validate_media_attachments


class VideoGenerationTests(unittest.TestCase):
    def test_all_resolutions_align_and_fit_model_canvas(self):
        self.assertEqual(set(VIDEO_RESOLUTION_DIMENSIONS), {"480p", "672p"})
        for resolution, expected in VIDEO_RESOLUTION_DIMENSIONS.items():
            with self.subTest(resolution=resolution):
                self.assertEqual(video_canvas_dimensions(resolution, "16:9"), expected)
                self.assertEqual(video_canvas_dimensions(resolution, "9:16"), expected[::-1])
                self.assertEqual(expected[0] % 32, 0)
                self.assertEqual(expected[1] % 32, 0)
                self.assertLessEqual(expected[0] * expected[1], VIDEO_MAX_PIXELS)

    def test_reference_image_controls_aspect_without_exceeding_budget(self):
        self.assertEqual(video_canvas_dimensions("480p", "16:9", (1080, 1920)), (480, 864))
        self.assertEqual(video_canvas_dimensions("672p", "9:16", (1600, 1200)), (896, 672))
        width, height = video_canvas_dimensions("672p", "16:9", (6000, 1000))
        self.assertLessEqual(width * height, VIDEO_MAX_PIXELS)
        self.assertEqual(width % 32, 0)
        self.assertEqual(height % 32, 0)

    def test_two_images_are_first_and_last_keyframes(self):
        graph = MiniMaxH3Runtime._build_workflow(
            "Uma cena", 42, "primeira.png", last_image="ultima.png", width=1344, height=768
        )
        self.assertEqual(graph["4"]["inputs"]["first_frame"], ["20", 0])
        self.assertEqual(graph["4"]["inputs"]["last_frame"], ["21", 0])
        self.assertEqual(graph["20"]["inputs"]["image"], "primeira.png")
        self.assertEqual(graph["21"]["inputs"]["image"], "ultima.png")
        self.assertEqual(graph["6"]["inputs"]["unet_name"], DIFFUSION_MODEL)

    def test_backend_rejects_other_formats_and_excess_images(self):
        image = {"type": "file", "content_type": "image/png", "name": "a.png"}
        pdf = {"type": "file", "content_type": "application/pdf", "name": "a.pdf"}
        message = {"role": "user", "files": [image, image, image]}
        with self.assertRaises(ValueError):
            _validate_media_attachments([message], message, "video", max_images=2)
        with self.assertRaises(ValueError):
            _validate_media_attachments([{"role": "user", "files": [pdf]}], None, "image", max_images=10)
        with self.assertRaises(ValueError):
            _validate_media_attachments([{"role": "user", "files": [image]}], None, "image", max_images=0)
        with self.assertRaises(ValueError):
            _validate_media_attachments([{"role": "user", "files": [image, image]}], None, "image", max_images=1)
        with self.assertRaises(ValueError):
            _validate_media_attachments([{"role": "user", "files": [{"type": "file", "content_type": "video/mp4", "name": "a.mp4"}]}], None, "music")
        _validate_media_attachments([{"role": "user", "files": [pdf]}], None, "music")

    def test_video_export_preserves_more_detail_without_changing_sampling(self):
        graph = MiniMaxH3Runtime._build_workflow("Uma cena", 42, "primeira.png", last_image="ultima.png")
        export = graph["16"]["inputs"]
        self.assertEqual(export["format"], "mp4")
        self.assertEqual(export["format.codec"], "h264")
        self.assertEqual(export["format.codec.encoding"], "re-encode")
        self.assertEqual(export["format.codec.encoding.crf"], VIDEO_OUTPUT_CRF)
        self.assertEqual(VIDEO_OUTPUT_CRF, 18.0)
        self.assertEqual(graph["9"]["inputs"]["steps"], 8)
        self.assertEqual(graph["15"]["inputs"]["fps"], 24.0)

    def test_runtime_lora_changes_only_its_application_mode(self):
        merged = MiniMaxH3Runtime._build_workflow("Uma cena", 42, "a.png", last_image="b.png")
        runtime = MiniMaxH3Runtime._build_workflow(
            "Uma cena", 42, "a.png", last_image="b.png", low_vram_lora=False
        )
        self.assertTrue(merged["7"]["inputs"]["low_vram"])
        self.assertFalse(runtime["7"]["inputs"]["low_vram"])
        runtime["7"]["inputs"]["low_vram"] = True
        self.assertEqual(merged, runtime)

    def test_detail_profile_requires_available_memory_and_validated_canvas(self):
        gib = 1024**3
        stats = {"devices": [{"type": "cuda", "vram_total": 16 * gib, "vram_free": 14 * gib}],
                 "system": {"ram_free": 18 * gib, "ram_total": 32 * gib}}
        for width, height in [(864, 480), (480, 704), (672, 672)]:
            self.assertFalse(_use_merged_video_lora(stats, width, height, 124))
        self.assertTrue(_use_merged_video_lora(stats, 1184, 672, 124))
        self.assertTrue(_use_merged_video_lora(stats, 864, 480, 192))
        self.assertTrue(_use_merged_video_lora(stats, 864, 480, 0))
        for field, value in [("type", "cpu"), ("vram_total", 12 * gib), ("vram_free", 9 * gib),
                             ("vram_free", float("nan")), ("vram_total", float("inf"))]:
            modified = {**stats, "devices": [{**stats["devices"][0], field: value}]}
            self.assertTrue(_use_merged_video_lora(modified, 864, 480, 124))
        self.assertTrue(_use_merged_video_lora({**stats, "system": {"ram_free": 11 * gib, "ram_total": 32 * gib}}, 864, 480, 124))
        self.assertTrue(_use_merged_video_lora({**stats, "system": {"ram_free": 14 * gib, "ram_total": 16 * gib}}, 864, 480, 124))
        for malformed in [None, {}, [], {"devices": []}, {"devices": [None]}]:
            self.assertTrue(_use_merged_video_lora(malformed, 864, 480, 124))

    def test_memory_recovery_only_matches_lora_or_sampling_errors(self):
        def event(node, kind="torch.OutOfMemoryError", message="CUDA out of memory"):
            return ["execution_error", {"node_id": node, "exception_type": kind, "exception_message": message}]
        for node in ["7", "12", 12]:
            self.assertTrue(_video_lora_out_of_memory([event(node)]))
        self.assertTrue(_video_lora_out_of_memory([event("12", "RuntimeError", "CUDA error: out of memory")]))
        for node in ["1", "4", "6", "14", "16"]:
            self.assertFalse(_video_lora_out_of_memory([event(node)]))
        self.assertFalse(_video_lora_out_of_memory([event("12", "ValueError", "Invalid shape")]))
        self.assertFalse(_video_lora_out_of_memory([["execution_start", event("12")[1]]]))
        self.assertFalse(_video_lora_out_of_memory([None, {}, ["execution_error", None]]))


class VideoGenerationRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_retry_keeps_seed_images_and_dimensions(self):
        runtime = MiniMaxH3Runtime()
        progress = AsyncMock()
        image = ("a.png", b"first", "image/png")
        last = ("b.png", b"last", "image/png")
        result = {"video": b"video", "filename": "a.mp4"}
        with patch.object(runtime, "_generate_once", AsyncMock(side_effect=[_VideoLoRAMemoryError(), result])) as once, \
             patch.object(runtime, "stop", AsyncMock()) as stop:
            self.assertEqual(await runtime.generate("Uma cena", progress, image, last, 672, 672), result)
        self.assertEqual(once.await_count, 2)
        first, second = [call.kwargs for call in once.await_args_list]
        self.assertEqual(second.pop("low_vram_lora"), True)
        self.assertEqual(first, second)
        self.assertEqual(first["image"], image)
        self.assertEqual(first["last_image"], last)
        self.assertEqual((first["width"], first["height"]), (672, 672))
        stop.assert_awaited_once()
        progress.assert_awaited_once()

    async def test_non_memory_failure_does_not_retry(self):
        runtime = MiniMaxH3Runtime()
        with patch.object(runtime, "_generate_once", AsyncMock(side_effect=RuntimeError("Invalid workflow"))) as once, \
             patch.object(runtime, "stop", AsyncMock()) as stop:
            with self.assertRaisesRegex(RuntimeError, "Invalid workflow"):
                await runtime.generate("Uma cena", AsyncMock())
        once.assert_awaited_once()
        stop.assert_not_awaited()

    async def test_cancellation_never_restarts_generation(self):
        runtime = MiniMaxH3Runtime()
        async def cancelled(**options):
            runtime._cancel_requested = True
            raise _VideoLoRAMemoryError()
        with patch.object(runtime, "_generate_once", AsyncMock(side_effect=cancelled)) as once:
            with self.assertRaises(asyncio.CancelledError):
                await runtime.generate("Uma cena", AsyncMock())
        once.assert_awaited_once()

    async def test_cancellation_during_retry_progress_never_restarts(self):
        runtime = MiniMaxH3Runtime()
        async def cancel(*args):
            runtime._cancel_requested = True
        with patch.object(runtime, "_generate_once", AsyncMock(side_effect=_VideoLoRAMemoryError())) as once, \
             patch.object(runtime, "stop", AsyncMock()):
            with self.assertRaises(asyncio.CancelledError):
                await runtime.generate("Uma cena", AsyncMock(side_effect=cancel))
        once.assert_awaited_once()

    async def test_cancellation_during_worker_shutdown_never_restarts(self):
        runtime = MiniMaxH3Runtime()
        async def cancel():
            runtime._cancel_requested = True
        with patch.object(runtime, "_generate_once", AsyncMock(side_effect=_VideoLoRAMemoryError())) as once, \
             patch.object(runtime, "stop", AsyncMock(side_effect=cancel)):
            with self.assertRaises(asyncio.CancelledError):
                await runtime.generate("Uma cena", AsyncMock())
        once.assert_awaited_once()

    async def test_normal_cancellation_does_not_retry(self):
        runtime = MiniMaxH3Runtime()
        with patch.object(runtime, "_generate_once", AsyncMock(side_effect=asyncio.CancelledError())) as once:
            with self.assertRaises(asyncio.CancelledError):
                await runtime.generate("Uma cena", AsyncMock())
        once.assert_awaited_once()

    async def test_memory_recovery_is_limited_to_one_retry(self):
        runtime = MiniMaxH3Runtime()
        with patch.object(runtime, "_generate_once", AsyncMock(side_effect=_VideoLoRAMemoryError())) as once, \
             patch.object(runtime, "stop", AsyncMock()) as stop:
            with self.assertRaises(_VideoLoRAMemoryError):
                await runtime.generate("Uma cena", AsyncMock())
        self.assertEqual(once.await_count, 2)
        stop.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
