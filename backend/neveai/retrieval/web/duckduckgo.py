import logging
from typing import Optional

from neveai.retrieval.web.main import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


def search_duckduckgo(
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
    concurrent_requests: Optional[int] = None,
    backend: Optional[str] = "auto",
    timeout: Optional[float] = None,
) -> list[SearchResult]:
    """
    Search using DuckDuckGo's Search API and return the results as a list of SearchResult objects.
    Args:
        query (str): The query to search for
        count (int): The number of results to return
        backend (str): The search backend to use (auto, duckduckgo, google, brave, etc.)

    Returns:
        list[SearchResult]: A list of search results
    """
    try:
        from ddgs import DDGS
        from ddgs.exceptions import RatelimitException
    except ImportError:
        log.warning("ddgs is not installed; DuckDuckGo web search is unavailable")
        return []

    # Use the DDGS context manager to create a DDGS object
    search_results = []
    with DDGS(timeout=timeout or 15) as ddgs:
        if concurrent_requests:
            ddgs.threads = concurrent_requests

        def collect_results(search_backend: str) -> list[dict]:
            collected = []
            seen_links = set()
            max_pages = 1 if count <= 25 else 6

            for page in range(1, max_pages + 1):
                try:
                    page_results = ddgs.text(
                        query,
                        safesearch="moderate",
                        max_results=count,
                        backend=search_backend,
                        page=page,
                    )
                except Exception:
                    if collected:
                        return collected
                    raise

                new_items = 0
                for result in page_results or []:
                    link = result.get("href")
                    if not link or link in seen_links:
                        continue
                    collected.append(result)
                    seen_links.add(link)
                    new_items += 1

                    if len(collected) >= count:
                        return collected

                if page > 1 and new_items == 0:
                    break

            return collected

        def merge_unique_results(base_results: list[dict], extra_results: list[dict]) -> list[dict]:
            merged = []
            seen_links = set()

            for result in [*base_results, *extra_results]:
                link = result.get("href")
                if not link or link in seen_links:
                    continue

                merged.append(result)
                seen_links.add(link)

                if len(merged) >= count:
                    break

            return merged

        candidate_backends = []
        for candidate in [backend, "duckduckgo", "auto", "bing", "brave", "yahoo"]:
            if candidate and candidate not in candidate_backends:
                candidate_backends.append(candidate)

        for search_backend in candidate_backends:
            try:
                search_results = merge_unique_results(
                    search_results,
                    collect_results(search_backend),
                )
                if len(search_results) >= count:
                    break
            except RatelimitException as e:
                log.warning(f"DDGS rate limit ({search_backend} backend): {e}")
            except Exception as e:
                log.warning(f"DDGS search error ({search_backend} backend): {e}")
    if filter_list:
        search_results = get_filtered_results(search_results, filter_list)

    # Return the list of search results
    return [
        SearchResult(
            link=result["href"],
            title=result.get("title"),
            snippet=result.get("body"),
        )
        for result in search_results
    ]
