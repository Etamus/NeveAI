import base64
import unittest
from unittest.mock import patch

from neveai.retrieval.web.bing import parse_bing_results
from neveai.retrieval.web.duckduckgo import search_duckduckgo


def item(url, title="A useful result", snippet="Source evidence"):
    return f'<li class="b_algo"><h2><a href="{url}">{title}</a></h2><div class="b_caption"><p>{snippet}</p></div></li>'


class SearchFallbackTests(unittest.TestCase):
    def test_decodes_redirects_deduplicates_and_ignores_navigation(self):
        url = "https://example.com/article?q=1"
        encoded = "a1" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        html = '<a href="https://example.org/navigation">Not a result</a>' + item("https://www.bing.com/ck/a?u=" + encoded)
        html += item(url) + item("javascript:alert(1)") + item("https://www.bing.com/ck/a?u=a1%%invalid")
        self.assertEqual(parse_bing_results(html, 5), [{"href": url, "title": "A useful result", "body": "Source evidence"}])
        self.assertEqual(len(parse_bing_results(item(url)+item("https://example.org/other"), 1)), 1)

    def test_malformed_links_do_not_discard_other_results(self):
        url = "https://example.org/article"
        self.assertEqual(parse_bing_results(item("https://[")+item(url), 2)[0]["href"], url)
        self.assertEqual(parse_bing_results(item(url), 0), [])

    def test_healthy_provider_never_uses_the_fallback(self):
        with patch("ddgs.DDGS") as cls, patch("neveai.retrieval.web.bing.search_bing_fallback") as fallback:
            cls.return_value.__enter__.return_value.text.return_value = [{"href":"https://example.com/","title":"Title","body":"Evidence"}]
            self.assertEqual(len(search_duckduckgo("any question", 3, timeout=2)), 1)
            fallback.assert_not_called()

    def test_empty_providers_use_fallback_for_the_original_question(self):
        with patch("ddgs.DDGS") as cls, patch("neveai.retrieval.web.bing.search_bing_fallback") as fallback:
            cls.return_value.__enter__.return_value.text.return_value = []
            fallback.return_value = [{"href":"https://example.com/","title":"Title","body":"Evidence"}]
            result = search_duckduckgo("An arbitrary question, not a GOT rule", 3, timeout=2)
            self.assertEqual(result[0].link, "https://example.com/")
            self.assertEqual(fallback.call_args.args[:2], ("An arbitrary question, not a GOT rule", 3))

    def test_domain_filters_are_preserved(self):
        with patch("ddgs.DDGS") as cls, patch("neveai.retrieval.web.bing.search_bing_fallback") as fallback, \
             patch("neveai.retrieval.web.duckduckgo.get_filtered_results", side_effect=lambda rows, _: [r for r in rows if "allowed" in r["href"]]):
            cls.return_value.__enter__.return_value.text.return_value = []
            fallback.return_value = [{"href":"https://allowed.example/","title":"Allowed"}, {"href":"https://blocked.example/","title":"Blocked"}]
            self.assertEqual(len(search_duckduckgo("question", 3, ["allowed"], timeout=2)), 1)

    def test_date_restrictions_do_not_fall_back_to_unfiltered_results(self):
        with patch("ddgs.DDGS") as cls, patch("neveai.retrieval.web.bing.search_bing_fallback") as fallback:
            cls.return_value.__enter__.return_value.text.return_value = []
            self.assertEqual(search_duckduckgo("today", 3, timeout=2, time_range="day"), [])
            fallback.assert_not_called()


if __name__ == "__main__": unittest.main()
