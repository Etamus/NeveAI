import unittest

from neveai.routers.video_generation import (
    DIFFUSION_MODEL,
    VIDEO_MAX_PIXELS,
    VIDEO_RESOLUTION_DIMENSIONS,
    MiniMaxH3Runtime,
    video_canvas_dimensions,
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


if __name__ == "__main__":
    unittest.main()
