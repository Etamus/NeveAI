import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from neveai.retrieval.web.research import research, diverse_sources, _searches
from neveai.routers.retrieval import SearchForm, process_web_search
from neveai.utils.middleware import complete_deep_search_queries, should_run_web_search_for_message


class DeepResearchTests(unittest.IsolatedAsyncioTestCase):
    def test_short_topics_respect_deep_research_toggle_but_not_greetings(self):
        self.assertTrue(should_run_web_search_for_message('Qwen benchmarks', True))
        self.assertFalse(should_run_web_search_for_message('Qwen benchmarks', False))
        self.assertFalse(should_run_web_search_for_message('Bom dia!', True))

    def test_planner_fallback_has_complementary_queries_without_changing_entities(self):
        query = 'Qual o melhor modelo Qwen3.5?'
        queries = complete_deep_search_queries(query, [query])
        self.assertEqual(len(queries), 3)
        self.assertTrue(all('Qwen3.5' in value for value in queries))
        self.assertIn('fontes oficiais', queries[1])
        self.assertIn('limitacoes', queries[2])
        planned = ['Qwen3.5 official', 'Qwen3.5 benchmarks', 'Qwen3.5 limitations']
        self.assertEqual(complete_deep_search_queries(query, planned), planned)
        drifting = complete_deep_search_queries(query, ['Qwen3.5 benchmarks', 'Best iPhone camera'])
        self.assertEqual(len(drifting), 3)
        self.assertFalse(any('iPhone' in value for value in drifting))
    def setUp(self):
        _searches.clear()
        self.config = SimpleNamespace(
            ENABLE_WEB_SEARCH=True, WEB_SEARCH_CONCURRENT_REQUESTS=0,
            ENABLE_WEB_LOADER_SSL_VERIFICATION=True, WEB_SEARCH_TRUST_ENV=False,
            WEB_SEARCH_ENGINE='ddgs', WEB_SEARCH_RESULT_COUNT=20,
            WEB_SEARCH_DOMAIN_FILTER_LIST=[], DDGS_BACKEND='auto', SEARXNG_QUERY_URL='',
            BYPASS_WEB_SEARCH_WEB_LOADER=False,
        )
        self.request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(config=self.config)),
            state=SimpleNamespace(deep_search_enabled=True),
        )
        self.user = SimpleNamespace(role='admin')

    @staticmethod
    def page(url):
        return {'content': 'Qwen benchmark results, capabilities and limitations. ' * 12,
                'metadata': {'source': url, 'title': 'Qwen evidence'}}

    def test_diversity_preserves_all_candidates_and_prioritizes_new_sites(self):
        items = [{'link': f'https://a.org/{i}'} for i in range(4)] + [
            {'link': 'https://b.org/one'}, {'link': 'https://www.c.org/one'}]
        ordered = diverse_sources(items, ['https://www.a.org/official'])
        self.assertEqual([item['link'] for item in ordered[:2]], ['https://b.org/one', 'https://www.c.org/one'])
        self.assertEqual(len(ordered), len(items))

    async def test_links_still_research_multiple_independent_sites(self):
        direct = 'https://qwen.ai/official'
        items = [{'link': f'https://site{i}.org/qwen', 'title': 'Qwen evaluation', 'snippet': 'Qwen evidence'} for i in range(12)]
        search = AsyncMock(return_value=items)
        with patch('neveai.retrieval.web.research.read_page', AsyncMock(side_effect=lambda session, url, *args: self.page(url))):
            result = await research(self.request, SearchForm(queries=['Qwen capabilities'], urls=[direct]), self.user, search)
        search.assert_awaited_once()
        self.assertEqual(result['pages_read_count'], 10)
        self.assertEqual(result['site_count'], 10)
        self.assertIn(direct, result['filenames'])
        self.assertEqual(result['snippet_count'], 0)
        self.assertLessEqual(sum(len(doc['content']) for doc in result['docs']), 50000)

    async def test_empty_pages_replaced_without_counting_snippets_as_read(self):
        items = [{'link': f'https://site{i}.org/qwen', 'title': 'Qwen evaluation', 'snippet': 'Qwen snippet'} for i in range(20)]
        def load(session, url, *args):
            index = int(url.split('site')[1].split('.')[0])
            return self.page(url) if index >= 8 else {'content': ' ', 'metadata': {'source': url}}
        with patch('neveai.retrieval.web.research.read_page', AsyncMock(side_effect=load)):
            result = await research(self.request, SearchForm(queries=['Qwen'], max_loaded_urls=10), self.user, AsyncMock(return_value=items))
        self.assertEqual(result['pages_read_count'], 10)
        self.assertEqual(result['snippet_count'], 0)

    async def test_blocked_pages_snippets_are_explicit_and_limited(self):
        items = [{'link': f'https://site{i}.org/qwen', 'title': 'Qwen', 'snippet': 'Qwen snippet'} for i in range(15)]
        with patch('neveai.retrieval.web.research.read_page', AsyncMock(return_value=None)):
            result = await research(self.request, SearchForm(queries=['Qwen']), self.user, AsyncMock(return_value=items))
        self.assertEqual(result['pages_read_count'], 0)
        self.assertEqual(result['site_count'], 0)
        self.assertEqual(result['snippet_count'], 2)
        self.assertTrue(all(doc['metadata']['snippet_only'] for doc in result['docs']))

    async def test_pipeline_budget_retains_completed_pages_and_cancels_slow_reads(self):
        cancelled = []
        async def load(session, url, *args):
            if 'slow' in url:
                try:
                    await asyncio.sleep(30)
                finally:
                    cancelled.append(url)
            return self.page(url)
        items = [{'link': 'https://fast.org/qwen', 'title': 'Qwen'}, {'link': 'https://slow.org/qwen', 'title': 'Qwen'}]
        with patch('neveai.retrieval.web.research.DEEP_RESEARCH_BUDGET', 0.1), patch('neveai.retrieval.web.research.read_page', load):
            result = await asyncio.wait_for(research(self.request, SearchForm(queries=['Qwen']), self.user, AsyncMock(return_value=items)), 1)
        self.assertEqual(result['pages_read_count'], 1)
        self.assertEqual(result['filenames'], ['https://fast.org/qwen'])
        self.assertEqual(cancelled, ['https://slow.org/qwen'])

    async def test_empty_results_are_not_reported_as_success(self):
        with patch('neveai.retrieval.web.research.read_page', AsyncMock(return_value={'content': '', 'metadata': {}})):
            result = await research(self.request, SearchForm(queries=['Qwen']), self.user, AsyncMock(return_value=[]))
        self.assertFalse(result['status'])
        self.assertEqual(result['loaded_count'], 0)

    async def test_route_uses_modern_pipeline_with_and_without_links(self):
        for urls in [[], ['https://qwen.ai']]:
            with patch('neveai.retrieval.web.research.research', AsyncMock(return_value={'status': True})) as modern:
                await process_web_search(self.request, SearchForm(queries=['Qwen'], urls=urls), self.user)
            modern.assert_awaited_once()

    async def test_queries_are_bounded_parallel_and_one_failure_keeps_other_evidence(self):
        active, peak = 0, 0
        async def run(func, request, engine, query, user, count):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.02)
                if query == 'fail':
                    raise RuntimeError('provider unavailable')
                return [{'link': 'https://example.org/' + query}]
            finally:
                active -= 1
        async def pipeline(request, form, user, search):
            return await search('ddgs', 20)
        with patch('neveai.retrieval.web.research.research', pipeline), patch('neveai.routers.retrieval.run_in_threadpool', run):
            result = await process_web_search(self.request, SearchForm(queries=['primary', 'fail', 'independent', 'ignored']), self.user)
        self.assertEqual(peak, 3)
        self.assertEqual(len(result), 2)

    async def test_normal_url_first_behavior_is_unchanged(self):
        self.request.state.deep_search_enabled = False
        search = AsyncMock()
        with patch('neveai.retrieval.web.research.read_page', AsyncMock(side_effect=lambda session, url, *args: self.page(url))):
            result = await research(self.request, SearchForm(queries=['Qwen'], urls=['https://qwen.ai']), self.user, search)
        search.assert_not_awaited()
        self.assertEqual(result['pages_read_count'], 1)

    async def test_model_family_does_not_include_unrelated_phone_results(self):
        search = AsyncMock(return_value=[{'link': 'https://phones.org', 'title': 'Best phone', 'snippet': 'iPhone'}, {'link': 'https://qwen.ai', 'title': 'Qwen language model', 'snippet': 'Qwen'}])
        with patch('neveai.retrieval.web.research.read_page', AsyncMock(side_effect=lambda session, url, *args: self.page(url))):
            result = await research(self.request, SearchForm(queries=['Best Qwen model'], question='Qual o melhor modelo Qwen?'), self.user, search)
        self.assertEqual(result['filenames'], ['https://qwen.ai'])
