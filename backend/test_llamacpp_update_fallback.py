import unittest

from neveai.utils.llamacpp_updates import (
    _release_from_assets, _release_tags, compatible_release, latest_compatible_release_tag,
)


class Response:
    def __init__(self, text="", payload=None, failed=False):
        self.body, self.payload, self.failed = text, payload, failed

    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def raise_for_status(self):
        if self.failed: raise RuntimeError("rate limited")
    async def text(self): return self.body
    async def json(self): return self.payload


class Session:
    def __init__(self, pages, releases=None, limited=True):
        self.pages, self.releases, self.limited = pages, releases or [], limited
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url.startswith("https://api.github.com/"):
            return Response(payload=self.releases, failed=self.limited)
        return Response(self.pages.get(url.rsplit("/llama.cpp/", 1)[-1], ""))


def link(tag, backend="cuda-13.4", architecture="x64"):
    name = f"llama-{tag}-bin-win-{backend}-{architecture}.zip"
    return f'<a href="/ggml-org/llama.cpp/releases/download/{tag}/{name}">{name}</a>'


class UpdateFallbackTests(unittest.IsolatedAsyncioTestCase):
    def test_parses_only_release_tags_and_manifest_assets(self):
        self.assertEqual(_release_tags('<a href="/ggml-org/llama.cpp/releases/tag/b12167">tag</a>'
                                      '<a href="/ggml-org/llama.cpp/releases/tag/invalid">bad</a>'), ["b12167"])
        self.assertTrue(compatible_release(_release_from_assets("b12167", link("b12167")), "cuda-13.4"))
        self.assertFalse(compatible_release(_release_from_assets("b12167", link("b12167", architecture="arm64")), "cuda-13.4"))
        self.assertTrue(compatible_release(_release_from_assets("b12167", link("b12167", "cuda-13.5")), "cuda-13.4"))
        self.assertFalse(compatible_release(_release_from_assets("b12167", link("b12167", "cuda-12.4")), "cuda-13.4"))
        self.assertFalse(compatible_release(_release_from_assets("b12167", link("b12166")), "cuda-13.4"))

    async def test_rate_limit_checks_older_releases_and_keeps_backend_compatibility(self):
        pages = {
            "releases?page=1": '<a href="/ggml-org/llama.cpp/releases/tag/b12190">new</a>',
            "releases?page=2": '<a href="/ggml-org/llama.cpp/releases/tag/b12189">new</a>',
            "releases?page=3": '<a href="/ggml-org/llama.cpp/releases/tag/b12167">compatible</a>'
                                '<a href="/ggml-org/llama.cpp/releases/tag/b12166">older</a>',
            "releases/expanded_assets/b12190": "",  # CI has not published assets yet.
            "releases/expanded_assets/b12189": link("b12189", "cuda-12.4"),
            "releases/expanded_assets/b12167": link("b12167"),
            "releases/expanded_assets/b12166": link("b12166"),
        }
        self.assertEqual(await latest_compatible_release_tag(Session(pages), "cuda-13.4"), "b12167")

    async def test_cpu_vulkan_and_cuda_major_never_cross(self):
        for backend in ("cpu", "vulkan", "cuda-12.4", "cuda-13.4"):
            pages = {"releases?page=1": '<a href="/ggml-org/llama.cpp/releases/tag/b12167">tag</a>',
                     "releases/expanded_assets/b12167": link("b12167", backend)}
            self.assertEqual(await latest_compatible_release_tag(Session(pages), backend), "b12167")
            pages["releases/expanded_assets/b12167"] = link("b12167", "cuda-12.4" if backend != "cuda-12.4" else "cpu")
            with self.assertRaisesRegex(RuntimeError, "rate limited"):
                await latest_compatible_release_tag(Session(pages), backend)

    async def test_api_success_keeps_the_original_path(self):
        session = Session({}, [_release_from_assets("b12167", link("b12167"))], limited=False)
        self.assertEqual(await latest_compatible_release_tag(session, "cuda-13.4"), "b12167")
        self.assertEqual(len(session.calls), 1)

    async def test_unknown_or_unpublished_assets_do_not_create_updates(self):
        with self.assertRaisesRegex(RuntimeError, "rate limited"):
            await latest_compatible_release_tag(Session({}), "cuda-13.4")


if __name__ == "__main__": unittest.main()
