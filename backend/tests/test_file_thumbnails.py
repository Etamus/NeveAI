import concurrent.futures
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from neveai.utils.file_thumbnails import get_image_thumbnail, THUMBNAIL_SIZE


class ImageThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cache = self.root / "cache"
        self.source = self.root / "original.png"
        Image.new("RGB", (2368, 1344), "#457e91").save(self.source)

    def tearDown(self):
        self.temporary.cleanup()

    def test_preview_is_bounded_and_original_is_unchanged(self):
        original = hashlib.sha256(self.source.read_bytes()).digest()
        target = get_image_thumbnail(self.source, self.cache)
        with Image.open(target) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, THUMBNAIL_SIZE)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(), original)

    def test_cache_hit_does_not_decode_again(self):
        target = get_image_thumbnail(self.source, self.cache)
        with patch("neveai.utils.file_thumbnails.Image.open", side_effect=AssertionError("Decoded twice")):
            self.assertEqual(get_image_thumbnail(self.source, self.cache), target)

    def test_source_changes_invalidate_cache(self):
        old = get_image_thumbnail(self.source, self.cache)
        stat = self.source.stat()
        os.utime(self.source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        new = get_image_thumbnail(self.source, self.cache)
        self.assertNotEqual(old, new)
        self.assertTrue(new.is_file())

    def test_tiny_images_are_not_upscaled(self):
        Image.new("RGB", (40, 30), "red").save(self.source)
        with Image.open(get_image_thumbnail(self.source, self.cache)) as image:
            self.assertEqual(image.size, (40, 30))

    def test_transparency_is_preserved(self):
        image = Image.new("RGBA", (1200, 900), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((300, 225, 900, 675), fill="red")
        image.save(self.source)
        with Image.open(get_image_thumbnail(self.source, self.cache)) as preview:
            self.assertEqual(preview.mode, "RGBA")
            self.assertEqual(preview.getpixel((0, 0))[3], 0)
            self.assertEqual(preview.getpixel((320, 240))[3], 255)

    def test_exif_orientation_is_applied(self):
        image = Image.new("RGB", (1200, 800), "red")
        ImageDraw.Draw(image).rectangle((0, 400, 1200, 800), fill="blue")
        exif = Image.Exif()
        exif[274] = 6
        source = self.root / "rotated.jpg"
        image.save(source, exif=exif, quality=95)
        with Image.open(get_image_thumbnail(source, self.cache)) as preview:
            self.assertGreater(preview.getpixel((100, 240))[2], 220)
            self.assertGreater(preview.getpixel((540, 240))[0], 220)

    def test_concurrent_requests_share_the_generated_file(self):
        with patch("neveai.utils.file_thumbnails.ImageOps.fit", wraps=ImageOps.fit) as fit:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                paths = list(pool.map(lambda _: get_image_thumbnail(self.source, self.cache), range(12)))
        self.assertEqual(len(set(paths)), 1)
        self.assertEqual(fit.call_count, 1)
        self.assertEqual(len(list(self.cache.glob("*.webp"))), 1)
        self.assertEqual(list(self.cache.glob("*.tmp")), [])

    def test_cold_decode_concurrency_is_bounded(self):
        sources = []
        for index in range(8):
            source = self.root / f"{index}.png"
            Image.new("RGB", (1000, 800), "red").save(source)
            sources.append(source)
        from PIL import ImageOps
        original_fit = ImageOps.fit
        active = 0
        maximum = 0
        lock = threading.Lock()

        def tracked(*args, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(active, maximum)
            try:
                time.sleep(0.02)
                return original_fit(*args, **kwargs)
            finally:
                with lock:
                    active -= 1

        with patch("neveai.utils.file_thumbnails.ImageOps.fit", side_effect=tracked):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda path: get_image_thumbnail(path, self.cache), sources))
        self.assertLessEqual(maximum, 2)

    def test_encoding_error_does_not_leave_partial_files(self):
        with patch.object(Image.Image, "save", side_effect=OSError("Disk full")):
            with self.assertRaises(OSError):
                get_image_thumbnail(self.source, self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_missing_and_non_image_sources_are_rejected(self):
        with self.assertRaises(FileNotFoundError):
            get_image_thumbnail(self.root / "missing.png", self.cache)
        self.source.write_text("Not an image")
        with self.assertRaises(UnidentifiedImageError):
            get_image_thumbnail(self.source, self.cache)


class ThumbnailRouteTests(unittest.TestCase):
    def setUp(self):
        from neveai.routers import files
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        self.module = files
        self.user = SimpleNamespace(id="owner", role="user")
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.png"
        Image.new("RGB", (1000, 800), "red").save(self.source)
        self.file = SimpleNamespace(id="test", user_id="owner", path=str(self.source), filename="source.png", meta={"content_type": "image/png"})
        self.lookup = patch.object(files.Files, "get_file_by_id", side_effect=lambda *args, **kwargs: self.file)
        self.access = patch.object(files, "has_access_to_file", return_value=False)
        self.cache = patch.object(files, "CACHE_DIR", self.root / "cache")
        for patcher in (self.lookup, self.access, self.cache):
            patcher.start()
            self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(files.router, prefix="/files")
        app.dependency_overrides[files.get_verified_user] = lambda: self.user
        app.dependency_overrides[files.get_session] = lambda: None
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.temporary.cleanup)

    def test_owner_gets_private_cached_webp_and_original_stays_original(self):
        response = self.client.get("/files/test/thumbnail?v=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/webp")
        self.assertEqual(response.headers["cache-control"], "private, max-age=3600")
        self.assertIn("Authorization", response.headers["vary"])
        original = self.client.get("/files/test/content")
        self.assertEqual(original.content, self.source.read_bytes())
        self.assertEqual(original.headers["content-type"], "image/png")

    def test_cache_never_bypasses_permission_checks(self):
        self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 200)
        self.user.id = "other"
        with patch.object(self.module, "get_image_thumbnail") as generate:
            self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 404)
            generate.assert_not_called()

    def test_shared_read_access_and_admin_access_work(self):
        self.user.id = "other"
        with patch.object(self.module, "has_access_to_file", return_value=True):
            self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 200)
        self.user.role = "admin"
        self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 200)

    def test_missing_records_paths_and_non_images(self):
        self.file = None
        self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 404)
        self.file = SimpleNamespace(id="test", user_id="owner", path=None, meta={"content_type": "image/png"})
        self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 404)
        self.file.path = str(self.root / "missing.png")
        self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 404)
        self.file.path = str(self.source)
        self.file.meta = {"content_type": "application/pdf"}
        self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 415)
        self.file.meta = {"content_type": None}
        self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 415)

    def test_corrupt_images_return_a_fallback_status(self):
        self.source.write_text("Not an image")
        self.assertEqual(self.client.get("/files/test/thumbnail").status_code, 415)
