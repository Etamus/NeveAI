import asyncio
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from neveai.models.files import File, Files
from neveai.retrieval.web.main import SearchResult
from neveai.retrieval.web.research import (
    extract_request_urls,
    huggingface_readme,
    extract_page,
    relevant_excerpt,
    PublicResolver,
    research,
    read_page,
    _pages,
    _searches,
    source_topic_terms,
    matches_source_topic,
)
from neveai.routers.retrieval import SearchForm
from neveai.utils.middleware import plan_chat_web_queries, filter_web_search_queries


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        File.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.context = patch(
            "neveai.models.files.get_db_context", lambda db=None: nullcontext(self.db)
        )
        self.context.start()
        samples = [
            ("image", "image/png", "qwen-image-2s", False, "me"),
            ("video", "video/mp4", "minimax-h3-fl2va-w4a8", False, "me"),
            ("audio", "audio/mpeg", "ace-step-1.5-turbo", False, "me"),
            ("pdf", "application/pdf", "file_generation", True, "me"),
            ("upload", "image/png", None, False, "me"),
            ("other", "image/png", "qwen-image-2s", False, "other"),
        ]
        for index, (id, mime, source, generated, owner) in enumerate(samples):
            self.db.add(
                File(
                    id=id,
                    filename=f"{id}.test",
                    user_id=owner,
                    meta={
                        "content_type": mime,
                        "data": {"source": source, "generated": generated},
                    },
                    created_at=index,
                    updated_at=index,
                )
            )
        self.db.commit()

    def tearDown(self):
        self.context.stop()
        self.db.close()
        self.engine.dispose()

    def test_excludes_uploads_and_other_users(self):
        self.assertEqual(
            {file["id"] for file in Files.get_generated_files("me")},
            {"image", "video", "audio", "pdf"},
        )

    def test_tabs_search_and_pagination(self):
        for kind, id in [
            ("image", "image"),
            ("video", "video"),
            ("audio", "audio"),
            ("document", "pdf"),
        ]:
            self.assertEqual(
                [file["id"] for file in Files.get_generated_files("me", kind)], [id]
            )
        self.assertEqual(len(Files.get_generated_files("me", query="video")), 1)
        self.assertEqual(Files.get_generated_files("me", query="%"), [])
        self.assertEqual(
            Files.get_generated_files("me", skip=1, limit=1)[0]["id"], "audio"
        )

    def test_deletion_removes_library_entry(self):
        self.db.delete(self.db.get(File, "image"))
        self.db.commit()
        self.assertEqual(Files.get_generated_files("me", "image"), [])


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_context_rejects_unrelated_results(self):
        terms = source_topic_terms("Compare v0.2.1 and v0.3 https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo")
        self.assertTrue(matches_source_topic({"title": "Qwen Image Viggle LoRA v0.3"}, terms))
        self.assertFalse(matches_source_topic({"title": "Qual e melhor Lula ou Flavio?", "snippet": "Compare two candidates"}, terms))
        self.assertFalse(matches_source_topic({"title": "Best cellphone image quality"}, terms))
        self.assertTrue(matches_source_topic({"title": "Any topic"}, set()))

    def setUp(self):
        _pages.clear()
        _searches.clear()
        self.config = SimpleNamespace(
            ENABLE_WEB_LOADER_SSL_VERIFICATION=True,
            WEB_SEARCH_TRUST_ENV=False,
            WEB_SEARCH_ENGINE="ddgs",
            WEB_SEARCH_RESULT_COUNT=5,
            WEB_SEARCH_DOMAIN_FILTER_LIST=[],
            DDGS_BACKEND="auto",
            SEARXNG_QUERY_URL="",
            BYPASS_WEB_SEARCH_WEB_LOADER=False,
        )
        self.request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(config=self.config)),
            state=SimpleNamespace(deep_search_enabled=False),
        )

    def test_urls_and_huggingface_raw(self):
        url = "https://huggingface.co/team/model"
        self.assertEqual(extract_request_urls(f"Compare ({url}). [{url}]"), [url])
        self.assertEqual(huggingface_readme(url), url + "/raw/main/README.md")
        self.assertEqual(
            huggingface_readme(url + "/blob/v0.3/README.md"),
            url + "/raw/v0.3/README.md",
        )
        self.assertEqual(extract_request_urls("https://user:secret@example.org"), [])

    def test_extraction_removes_navigation_and_keeps_table(self):
        html = "<html><title>Versions</title><nav>LOGIN FOOTER</nav><main><h1>Comparison</h1><p>Version 0.3 has nine steps and improved image quality.</p><table><tr><td>0.2</td><td>7 steps</td></tr><tr><td>0.3</td><td>9 steps</td></tr></table></main><footer>COOKIE</footer></html>"
        result = extract_page(html, "https://example.org", "text/html")
        self.assertIn("0.3", result["content"])
        self.assertIn("7 steps", result["content"])
        self.assertNotIn("LOGIN", result["content"])

    def test_excerpt_keeps_late_relevant_content(self):
        content = (
            "Noise " * 6000 + "VERSION Q6_K has better precision than Q4_K_M. " * 50
        )
        self.assertIn("Q6_K", relevant_excerpt(content, "Compare Q6_K and Q4_K_M"))

    async def test_resolver_blocks_private_and_mixed_dns(self):
        resolver = PublicResolver()
        try:
            for hosts in [["127.0.0.1"], ["8.8.8.8", "192.168.1.3"], ["::1"]]:
                with patch(
                    "aiohttp.resolver.DefaultResolver.resolve",
                    AsyncMock(return_value=[{"host": host} for host in hosts]),
                ):
                    with self.assertRaises(ValueError):
                        await resolver.resolve("example.org")
        finally:
            await resolver.close()

    async def test_direct_link_bypasses_search(self):
        page = {
            "content": "v0.2 uses seven steps; v0.3 uses nine steps. " * 20,
            "metadata": {"source": "https://example.org", "title": "Model"},
        }
        search = AsyncMock()
        with patch(
            "neveai.retrieval.web.research.read_page", AsyncMock(return_value=page)
        ):
            result = await research(
                self.request,
                SearchForm(
                    queries=["Compare 0.2 and 0.3"], urls=["https://example.org"]
                ),
                None,
                search,
            )
        self.assertTrue(result["status"])
        search.assert_not_awaited()

    async def test_best_model_search_filters_phone_results_and_finds_other_qwen_models(self):
        url = "https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF"
        page = {"content": "Qwen3.5 0.8B is a small language model. " * 12, "metadata": {"source": url, "title": "Qwen"}}
        search = AsyncMock(return_value=[SearchResult(link="https://example.org/iphone",title="Best model iPhone 16",snippet="Cellphone comparison"), SearchResult(link="https://qwen.ai/models",title="Qwen latest flagship models",snippet="Qwen language models ranked by capability")])
        with patch("neveai.retrieval.web.research.read_page", AsyncMock(side_effect=lambda session, link, *args: page if link == url else {"content": "Qwen flagship language models and evaluation results. " * 12, "metadata": {"source": link, "title": "Qwen models"}})):
            result = await research(self.request, SearchForm(queries=["Qwen best language model currently"],urls=[url],question=f"Best Qwen model {url}",search_after_urls=True),None,search)
        search.assert_awaited_once()
        self.assertIn("https://qwen.ai/models", result["filenames"])
        self.assertNotIn("iphone", str(result).lower())

    async def test_failed_read_falls_back_to_snippet_and_caches_search(self):
        search = AsyncMock(
            return_value=[
                SearchResult(
                    link="https://example.org",
                    title="Test",
                    snippet="Verified search snippet",
                )
            ]
        )
        with patch(
            "neveai.retrieval.web.research.read_page", AsyncMock(return_value=None)
        ):
            for _ in range(2):
                result = await research(
                    self.request, SearchForm(queries=["test"]), None, search
                )
        self.assertTrue(result["docs"][0]["metadata"]["snippet_only"])
        search.assert_awaited_once()

    async def test_missing_requested_version_triggers_supplementary_search(self):
        page = {
            "content": "v0.3 has nine steps. " * 20,
            "metadata": {"source": "https://example.org"},
        }
        search = AsyncMock(return_value=[])
        with patch(
            "neveai.retrieval.web.research.read_page", AsyncMock(return_value=page)
        ):
            result = await research(
                self.request,
                SearchForm(
                    queries=["Compare v0.2 and v0.3"], urls=["https://example.org"]
                ),
                None,
                search,
            )
        search.assert_awaited_once()
        self.assertTrue(result["status"])

    def test_balanced_parentheses_in_url_are_preserved(self):
        url = "https://en.wikipedia.org/wiki/Example_(film)"
        self.assertEqual(extract_request_urls(f"[source]({url})"), [url])

    async def test_partial_page_failures_do_not_discard_successes(self):
        page = {
            "content": "Valid page content. " * 20,
            "metadata": {"source": "https://example.org"},
        }
        with patch(
            "neveai.retrieval.web.research.read_page",
            AsyncMock(side_effect=[ValueError("bad"), page]),
        ):
            result = await research(
                self.request,
                SearchForm(
                    queries=["test"], urls=["https://bad.org", "https://example.org"]
                ),
                None,
                AsyncMock(return_value=[]),
            )
        self.assertEqual(result["loaded_count"], 1)

    async def test_no_results_are_explicitly_reported(self):
        result = await research(
            self.request, SearchForm(queries=["test"]), None, AsyncMock(return_value=[])
        )
        self.assertFalse(result["status"])

    async def test_failed_repository_read_does_not_accept_unrelated_search_snippets(self):
        url = "https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo"
        results = [SearchResult(link="https://example.org/politics", title="Qual e melhor entre os dois", snippet="A comparison of politicians"), SearchResult(link="https://example.org/qwen", title="Viggle Qwen Image", snippet="Qwen Image Viggle v0.3 comparison with v0.2.1")]
        with patch("neveai.retrieval.web.research.read_page", AsyncMock(return_value=None)):
            result = await research(self.request, SearchForm(queries=["Compare Viggle v0.2.1 v0.3"], urls=[url], question=f"Compare v0.2.1 v0.3 {url}"), None, AsyncMock(return_value=results))
        self.assertEqual(result["filenames"], ["https://example.org/qwen"])
        self.assertNotIn("politics", str(result))

    async def test_private_literal_blocked_before_fetch(self):
        session = SimpleNamespace(get=unittest.mock.Mock())
        with patch("neveai.retrieval.web.research.validate_url", return_value=True):
            self.assertIsNone(await read_page(session, "http://127.0.0.1/secrets"))
        session.get.assert_not_called()


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_simple_request_has_no_extra_model_call(self):
        with patch(
            "neveai.utils.middleware.generate_chat_completion", AsyncMock()
        ) as model:
            result = await plan_chat_web_queries(
                SimpleNamespace(app=True),
                {
                    "messages": [
                        {"role": "user", "content": "Qual a capital da Franca?"}
                    ],
                    "model": "local",
                },
                None,
                "Qual a capital da Franca",
            )
        model.assert_not_awaited()
        self.assertEqual(result, ["Qual a capital da Franca"])

    async def test_contextual_plan_uses_fast_bounded_inference(self):
        response = {
            "choices": [
                {"message": {"content": '{"queries":["O Rato Netflix sinopse"]}'}}
            ]
        }
        with patch(
            "neveai.utils.middleware.generate_chat_completion",
            AsyncMock(return_value=response),
        ) as model:
            result = await plan_chat_web_queries(
                SimpleNamespace(app=True),
                {
                    "messages": [{"role": "user", "content": "Me refiro a Netflix"}],
                    "model": "local",
                },
                None,
                'Do que se trata "O Rato" Me refiro a Netflix',
            )
        self.assertEqual(result, ["O Rato Netflix sinopse"])
        self.assertTrue(model.call_args.kwargs["form_data"]["no_think"])
        self.assertLessEqual(model.call_args.kwargs["form_data"]["max_tokens"], 240)
        self.assertEqual(
            filter_web_search_queries(result, "original", 1, prefer_generated=True),
            result,
        )

    async def test_invalid_json_or_missing_version_falls_back(self):
        for content in ["not JSON", '{"queries":["compare version 0.2"]}']:
            with patch(
                "neveai.utils.middleware.generate_chat_completion",
                AsyncMock(
                    return_value={"choices": [{"message": {"content": content}}]}
                ),
            ):
                result = await plan_chat_web_queries(
                    SimpleNamespace(app=True),
                    {
                        "messages": [
                            {"role": "user", "content": "Compare 0.2 and 0.3"}
                        ],
                        "model": "local",
                    },
                    None,
                    "Compare 0.2 and 0.3",
                )
            self.assertEqual(result, ["Compare 0.2 and 0.3"])

    async def test_planner_error_has_safe_fallback(self):
        with patch(
            "neveai.utils.middleware.generate_chat_completion",
            AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            result = await plan_chat_web_queries(
                SimpleNamespace(app=True),
                {
                    "messages": [{"role": "user", "content": "Me refiro a Netflix"}],
                    "model": "local",
                },
                None,
                "O Rato Netflix",
            )
        self.assertEqual(result, ["O Rato Netflix"])


if __name__ == "__main__":
    unittest.main()
