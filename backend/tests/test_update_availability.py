import unittest

from neveai.utils.llamacpp_updates import (
    compatible_backend, compatible_release, installed_backend, latest_compatible_release_tag,
)


def release(tag, *backends):
    return {"tag_name": tag, "assets": [{"name": f"llama-{tag}-bin-win-{backend}-x64.zip"} for backend in backends]}


class Response:
    def __init__(self, data=None, text="", status=200):
        self.data, self.content, self.status = data, text, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self.data

    async def text(self):
        return self.content


class Session:
    def __init__(self, releases=None, feed="", available=(), api_status=200):
        self.releases, self.feed, self.available, self.api_status = releases, feed, available, api_status
        self.head_calls = []

    def get(self, url, **kwargs):
        if url.endswith(".atom"):
            return Response(text=self.feed)
        return Response(data=self.releases, status=self.api_status)

    def head(self, url, **kwargs):
        self.head_calls.append(url)
        return Response(status=200 if any(url.endswith(name) for name in self.available) else 404)


class BackendCompatibilityTests(unittest.TestCase):
    def test_asset_is_preferred_over_display_label(self):
        self.assertEqual(installed_backend({"backend": "NVIDIA CUDA 13", "asset": "llama-b11716-bin-win-cuda-13.4-x64.zip"}), "cuda-13.4")

    def test_legacy_display_labels(self):
        for name, expected in [("NVIDIA CUDA 13", "cuda-13"), ("CUDA 12.4", "cuda-12"), ("CPU", "cpu"), ("Vulkan", "vulkan")]:
            with self.subTest(name=name):
                self.assertEqual(installed_backend({"backend": name}), expected)

    def test_backend_families_match_installer(self):
        for current, candidate, expected in [("cuda-13.4", "cuda-cu13.3", True), ("cuda-13.4", "cpu", False), ("cuda-13.4", "cuda-12.4", False), ("cpu", "vulkan", False), ("vulkan", "vulkan", True)]:
            with self.subTest(current=current, candidate=candidate):
                self.assertEqual(compatible_backend(current, candidate), expected)

    def test_cpu_only_release_does_not_update_cuda(self):
        self.assertFalse(compatible_release(release("b11717", "cpu", "vulkan"), "cuda-13.4"))
        self.assertTrue(compatible_release(release("b11716", "cuda-13.4"), "cuda-13.4"))

    def test_rejects_drafts_missing_assets_and_runtime_only(self):
        for data in [None, {}, {**release("b11717", "cuda-13.4"), "draft": True}, {"tag_name": "b11717", "assets": [{"name": "cudart-llama-bin-win-cuda-13.4-x64.zip"}]}, release("invalid", "cuda-13.4")]:
            with self.subTest(data=data):
                self.assertFalse(compatible_release(data, "cuda-13.4"))


class LatestReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_selects_installed_backend_not_newest_cpu_release(self):
        session = Session([release("b11717", "cpu"), release("b11716", "cuda-13.4")])
        self.assertEqual(await latest_compatible_release_tag(session, "cuda-13.4"), "b11716")
        self.assertEqual(await latest_compatible_release_tag(session, "cpu"), "b11717")

    async def test_accepts_a_real_new_cuda_release(self):
        self.assertEqual(await latest_compatible_release_tag(Session([release("b11718", "cuda-cu13.4")]), "cuda-13.4"), "b11718")

    async def test_atom_feed_requires_a_downloadable_package(self):
        session = Session(feed='<link href="/releases/tag/b11717"/><link href="/releases/tag/b11716"/>', available=("llama-b11716-bin-win-cuda-13.4-x64.zip",), api_status=403)
        self.assertEqual(await latest_compatible_release_tag(session, "cuda-13.4"), "b11716")
        self.assertTrue(session.head_calls)
        self.assertTrue(all("cuda-" in url for url in session.head_calls))

    async def test_unverified_feed_does_not_report_an_update(self):
        session = Session(feed='<link href="/releases/tag/b99999"/>', api_status=403)
        with self.assertRaises(RuntimeError):
            await latest_compatible_release_tag(session, "cuda-13.4")

    async def test_invalid_feed_tags_are_not_requested(self):
        session = Session(feed='<link href="/releases/tag/not-a-release"/>', api_status=403)
        with self.assertRaises(RuntimeError):
            await latest_compatible_release_tag(session, "cpu")
        self.assertEqual(session.head_calls, [])


if __name__ == "__main__":
    unittest.main()
