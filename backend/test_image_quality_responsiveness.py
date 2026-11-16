"""Pixel-equivalent reference processing outside the request event loop."""
import asyncio
import io
import threading
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image, ImageOps
from neveai.routers import image_quality_generation as quality


def previous_encoding(raw, size, planning_size):
    with Image.open(io.BytesIO(raw)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        planning_raw = None
        if planning_size is not None and planning_size != size:
            output = io.BytesIO()
            image.resize(planning_size, Image.Resampling.LANCZOS).save(output, format="PNG")
            planning_raw = output.getvalue()
        if size != image.size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="PNG")
        encoded = output.getvalue()
        return encoded, (planning_raw if planning_raw is not None else encoded) if planning_size is not None else None


class QualityResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_reference_counts_planner_dimensions_and_retry_inputs(self):
        output = io.BytesIO()
        Image.new("RGB", (93, 61), (120, 50, 90)).save(output, "PNG")
        raw = output.getvalue()
        for count in (0, 1, 4, 10):
            for retry in (None, "previous successful planner"):
                runtime = quality.NeveImage21Runtime()
                runtime._retry_prompt = retry
                runtime._ensure_models = AsyncMock(return_value=quality.EDIT_MODEL_FILE)
                runtime._plan_edit = AsyncMock(return_value="prepared prompt")
                runtime._start_comfy = AsyncMock(side_effect=RuntimeError("stop before GPU"))
                runtime._stop = AsyncMock()
                dimensions = AsyncMock()
                with patch.object(quality, "_read_image_reference_bytes", return_value=raw):
                    with self.assertRaisesRegex(RuntimeError, "stop before GPU"):
                        await runtime._run_once("edit", "1:1", ["ref"] * count, None, AsyncMock(), dimensions)
                runtime._stop.assert_awaited_once()
                if count and retry is None:
                    runtime._plan_edit.assert_awaited_once()
                    planner_inputs = runtime._plan_edit.await_args.args[1]
                    self.assertEqual(len(planner_inputs), count)
                    for index, encoded in enumerate(planner_inputs):
                        expected = runtime._reference_size(93, 61, quality.EDIT_MODEL_FILE, index, count, detail_canvas=False)
                        with Image.open(io.BytesIO(encoded)) as image:
                            self.assertEqual(image.size, expected)
                else:
                    runtime._plan_edit.assert_not_awaited()
                expected = runtime._reference_size(93, 61, quality.EDIT_MODEL_FILE, 0, count, optimized_edit=True) if count else runtime._generation_size("1:1")
                dimensions.assert_awaited_once_with(*expected)

    async def test_planner_hardware_detection_is_off_event_loop(self):
        runtime = quality.NeveImage21Runtime()
        main_thread = threading.get_ident()
        threads = []
        def pe_file():
            threads.append(threading.get_ident())
            return quality.PE_FILE
        with patch.object(runtime, "_pe_file", side_effect=pe_file), patch.object(runtime, "_start", side_effect=RuntimeError("stop before GPU")), patch.object(runtime, "_stop", new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError, "stop before GPU"):
                await runtime._plan_edit("edit", [], AsyncMock())
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0], main_thread)

    def test_exact_bytes_for_formats_orientation_and_retry(self):
        for mode, fmt in (("RGB", "PNG"), ("RGBA", "PNG"), ("P", "PNG"), ("L", "PNG"), ("RGB", "JPEG")):
            for orientation in range(1, 9):
                image = Image.new(mode, (93, 61))
                image.putpixel((12, 24), (120, 50, 90, 180)[:len(image.getbands())] if mode in ("RGB", "RGBA") else 123)
                exif = Image.Exif()
                exif[274] = orientation
                output = io.BytesIO()
                image.save(output, fmt, exif=exif)
                raw = output.getvalue()
                dimensions = (61, 93) if orientation >= 5 else (93, 61)
                self.assertEqual(quality._reference_dimensions(raw), dimensions)
                for size in (dimensions, (128, 96)):
                    for planning_size in (None, size, (64, 32)):
                        with self.subTest(mode=mode, orientation=orientation, size=size, planning=planning_size):
                            self.assertEqual(quality._encode_reference(raw, size, planning_size), previous_encoding(raw, size, planning_size))

    def test_corrupt_images_still_fail(self):
        for operation in (quality._reference_dimensions, lambda raw: quality._encode_reference(raw, (64, 64), None)):
            with self.assertRaises(OSError):
                operation(b"not an image")

    async def test_reference_worker_does_not_block_or_mutate_runtime_after_cancel(self):
        runtime = quality.NeveImage21Runtime()
        entered, release = threading.Event(), threading.Event()
        loop_thread = threading.get_ident()
        observed = []

        def encode(*args):
            observed.append(threading.get_ident())
            entered.set()
            release.wait(5)
            return b"encoded", b"planner"

        runtime._retry_prompt = None
        runtime._ensure_models = AsyncMock(return_value=quality.EDIT_MODEL_FILE)
        runtime._stop = AsyncMock()
        with patch.object(quality, "_read_image_reference_bytes", return_value=b"raw"), patch.object(quality, "_reference_dimensions", return_value=(640, 480)), patch.object(quality, "_encode_reference", side_effect=encode):
            task = asyncio.create_task(runtime._run_once("edit", "auto", ["reference"], None, AsyncMock()))
            try:
                async with asyncio.timeout(5):
                    while not entered.is_set():
                        await asyncio.sleep(.005)
                self.assertNotEqual(observed, [loop_thread])
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertFalse(runtime._lock.locked())
                self.assertIsNone(runtime._retry_prompt)
                runtime._stop.assert_awaited_once()
            finally:
                release.set()


if __name__ == "__main__":
    unittest.main()
