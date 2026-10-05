"""Bounded, URL-first research for chat; file retrieval remains independent."""

import asyncio
import ipaddress
import logging
import re
import time
from collections import OrderedDict
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp
from bs4 import BeautifulSoup

from neveai.utils.url import validate_url

log = logging.getLogger(__name__)
_pages = OrderedDict()
_searches = OrderedDict()
MAX_BYTES = 2 * 1024 * 1024
DEEP_RESEARCH_BUDGET = 42


def source_host(url):
    try:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def diverse_sources(items, existing=()):
    """Read independent sites first, without discarding useful pages from one site."""
    counts = {}
    for url in existing:
        host = source_host(url)
        counts[host] = counts.get(host, 0) + 1
    remaining, ordered = list(items), []
    while remaining:
        index = min(
            range(len(remaining)),
            key=lambda i: counts.get(source_host(remaining[i]["link"]), 0),
        )
        item = remaining.pop(index)
        host = source_host(item["link"])
        counts[host] = counts.get(host, 0) + 1
        ordered.append(item)
    return ordered


def extract_request_urls(text: str) -> list[str]:
    urls = []
    for value in re.findall(r"https?://[^\s<>\"']+", text or ""):
        value = value.rstrip(".,;:!?")
        for opening, closing in [("(", ")"), ("[", "]"), ("{", "}")]:
            while value.endswith(closing) and value.count(closing) > value.count(
                opening
            ):
                value = value[:-1]
        parsed = urlsplit(value)
        if parsed.hostname and not parsed.username and not parsed.password:
            value = urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
            )
            if value not in urls:
                urls.append(value)
    return urls[:4]


def huggingface_readme(url: str) -> str:
    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname != "huggingface.co":
        return url
    if parts and parts[0] in {"datasets", "spaces"}:
        return url
    if len(parts) == 2:
        return f"https://huggingface.co/{parts[0]}/{parts[1]}/raw/main/README.md"
    if len(parts) >= 5 and parts[2] == "blob":
        return url.replace("/blob/", "/raw/", 1)
    return url


def _get(cache, key):
    entry = cache.get(key)
    if entry and entry[0] > time.monotonic():
        cache.move_to_end(key)
        return entry[1]
    cache.pop(key, None)
    return None


def _put(cache, key, value, ttl=300):
    cache[key] = (time.monotonic() + ttl, value)
    cache.move_to_end(key)
    while len(cache) > 64:
        cache.popitem(last=False)


class PublicResolver(aiohttp.resolver.DefaultResolver):
    async def resolve(self, host, port=0, family=0):
        results = await super().resolve(host, port, family)
        if not results or any(
            not ipaddress.ip_address(item["host"]).is_global for item in results
        ):
            raise ValueError("Non-public address blocked")
        return results


def extract_page(text: str, url: str, content_type: str) -> dict:
    title = url
    if "html" in content_type or text.lstrip().lower().startswith(
        ("<!doctype html", "<html")
    ):
        soup = BeautifulSoup(text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else url
        try:
            from trafilatura import extract

            content = (
                extract(
                    text,
                    url=url,
                    include_comments=False,
                    include_tables=True,
                    fast=True,
                    favor_precision=True,
                )
                or ""
            )
        except ImportError:
            content = ""
        if len(content) < 100:
            for node in soup.select(
                "script, style, nav, footer, header, aside, noscript"
            ):
                node.decompose()
            main = soup.find("main") or soup.find("article") or soup
            content = main.get_text("\n", strip=True)
    else:
        content = text
    return {
        "content": content[:80000].strip(),
        "metadata": {"source": url, "title": title, "link": url},
    }


async def read_page(session, url: str, verify_ssl=True, trust_env=False) -> dict | None:
    cache_key = (url, verify_ssl, trust_env)
    try:
        if not await asyncio.to_thread(validate_url, url):
            return None
        cached = _get(_pages, cache_key)
        if cached:
            return {"content": cached["content"], "metadata": dict(cached["metadata"])}
        target = huggingface_readme(url)
        for initial in dict.fromkeys([target, url]):
            current = initial
            try:
                for _ in range(4):
                    if not await asyncio.to_thread(validate_url, current):
                        raise ValueError("Invalid URL")
                    parsed = urlsplit(current)
                    if parsed.username or parsed.password:
                        raise ValueError("URL credentials blocked")
                    if parsed.hostname:
                        try:
                            address = ipaddress.ip_address(parsed.hostname)
                        except ValueError:
                            address = None
                        if address is not None and not address.is_global:
                            raise ValueError("Non-public address blocked")
                    async with session.get(
                        current,
                        allow_redirects=False,
                        ssl=None if verify_ssl else False,
                    ) as response:
                        if response.status in {301, 302, 303, 307, 308}:
                            current = urljoin(
                                current, response.headers.get("Location", "")
                            )
                            continue
                        response.raise_for_status()
                        mime = response.headers.get("Content-Type", "").lower()
                        if not (
                            mime.startswith("text/") or "json" in mime or "xml" in mime
                        ):
                            raise ValueError("Unsupported page format")
                        if (
                            response.content_length
                            and response.content_length > MAX_BYTES
                        ):
                            raise ValueError("Page too large")
                        chunks, size = [], 0
                        async for chunk in response.content.iter_chunked(65536):
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise ValueError("Page too large")
                            chunks.append(chunk)
                        text = b"".join(chunks).decode(
                            response.charset or "utf-8", errors="replace"
                        )
                        page = await asyncio.to_thread(extract_page, text, url, mime)
                        page["metadata"]["fetched_url"] = current
                        if page["content"]:
                            _put(_pages, cache_key, page)
                            return {
                                "content": page["content"],
                                "metadata": dict(page["metadata"]),
                            }
                        break
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
                log.debug("Unable to read %s: %s", current, error)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError) as error:
        log.debug("Unable to read %s: %s", url, error)
    return None


def relevant_excerpt(content: str, question: str, limit=10000) -> str:
    if len(content) <= limit:
        return content
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "what",
        "which",
        "does",
        "que",
        "qual",
        "quais",
        "como",
        "uma",
        "para",
        "por",
        "com",
        "esse",
        "essa",
        "nesse",
        "nessa",
        "entre",
        "difference",
        "diferenca",
        "diferença",
        "compare",
    }
    terms = set(re.findall(r"[\w.-]{3,}", question.lower())) - stopwords
    chunks = [content[index : index + 1600] for index in range(0, len(content), 1400)]
    ranked = sorted(
        range(len(chunks)),
        key=lambda index: sum(term in chunks[index].lower() for term in terms),
        reverse=True,
    )
    chosen, size = {0}, len(chunks[0])
    for index in ranked:
        if index not in chosen and size + len(chunks[index]) <= limit:
            chosen.add(index)
            size += len(chunks[index])
    return "\n[...]\n".join(chunks[index] for index in sorted(chosen))[:limit]


def source_topic_terms(question):
    """Only use distinctive repository identifiers as hard relevance constraints."""
    terms = set()
    ignored = {"image", "model", "models", "turbo", "main", "readme", "instruct", "official", "uncensored", "gguf", "safetensors"}
    for url in extract_request_urls(question):
        parsed = urlsplit(url)
        if parsed.hostname != "huggingface.co":
            continue
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            terms.update(word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9]{3,}", parts[1]) if word.lower() not in ignored)
    terms.update(match.lower() for match in re.findall(r"\b(Qwen|Llama|Gemma|Mistral|DeepSeek)(?=\d|\b)", question, re.IGNORECASE))
    return terms


def matches_source_topic(item, terms):
    if not terms:
        return True
    text = " ".join(str(item.get(key) or "") for key in ("link", "title", "snippet")).lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z])", text) for term in terms)


async def research(request, form, user, search):
    config = request.app.state.config
    deep = bool(getattr(request.state, "deep_search_enabled", False))
    max_pages = max(1, min(form.max_loaded_urls or (10 if deep else 4), 10 if deep else 4))
    deadline = time.monotonic() + DEEP_RESEARCH_BUDGET
    verify = config.ENABLE_WEB_LOADER_SSL_VERIFICATION
    trust = config.WEB_SEARCH_TRUST_ENV
    items, docs = [], []
    topic_terms = source_topic_terms(form.question or " ".join(form.queries))
    timeout = aiohttp.ClientTimeout(total=10 if deep else 6, connect=3)
    connector = aiohttp.TCPConnector(resolver=PublicResolver(), limit=6)
    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        trust_env=trust,
        headers={
            "User-Agent": "NeveAI/1.0 (web research)",
            "Accept": "text/html,text/plain,application/json",
        },
    ) as session:

        async def read_many(urls):
            if not urls:
                return []
            tasks = [
                asyncio.create_task(
                    asyncio.wait_for(
                        read_page(session, url, verify, trust),
                        timeout=12 if deep else 7,
                    )
                )
                for url in urls
            ]
            try:
                done, _ = await asyncio.wait(
                    tasks,
                    timeout=max(0, deadline - time.monotonic()) if deep else 7,
                )
                pages = []
                for task in tasks:
                    if task not in done or task.cancelled() or task.exception() is not None:
                        continue
                    page = task.result()
                    if isinstance(page, dict) and len(page.get("content", "").strip()) >= 80:
                        pages.append(page)
                return pages
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

        direct = list(dict.fromkeys(form.urls))[:min(4, max_pages)]
        if direct:
            docs = await read_many(direct)
            items = [{"link": url, "title": url, "snippet": ""} for url in direct]

        requested_versions = re.findall(
            r"\bv?(\d+(?:\.\d+)+)\b", form.question or " ".join(form.queries)
        )
        direct_text = " ".join(doc["content"] for doc in docs)
        missing_versions = bool(direct) and any(
            version not in direct_text for version in requested_versions
        )
        # Read supplied URLs first; deep research also seeks independent evidence.
        if deep or form.search_after_urls or not docs or len(docs) < len(direct) or missing_versions:
            engine = form.engine or config.WEB_SEARCH_ENGINE
            count = form.result_count or config.WEB_SEARCH_RESULT_COUNT
            key = (
                engine,
                tuple(form.queries),
                count,
                str(config.WEB_SEARCH_DOMAIN_FILTER_LIST),
                str(config.DDGS_BACKEND),
                str(config.SEARXNG_QUERY_URL),
                deep,
            )
            results = _get(_searches, key)
            if results is None:
                try:
                    if deep:
                        results = await asyncio.wait_for(
                            search(engine, count),
                            timeout=max(0, deadline - time.monotonic()),
                        )
                    else:
                        results = await search(engine, count)
                except asyncio.TimeoutError:
                    results = []
                if results:
                    _put(_searches, key, results, 120)
            seen = {item["link"] for item in items}
            for result in results or []:
                item = (
                    result.model_dump()
                    if hasattr(result, "model_dump")
                    else dict(result)
                )
                if item.get("link") and item["link"] not in seen and matches_source_topic(item, topic_terms):
                    items.append(item)
                    seen.add(item["link"])
            loaded = {doc["metadata"]["source"] for doc in docs}
            versions = re.findall(
                r"\bv?(\d+(?:\.\d+)+)\b", form.question or " ".join(form.queries)
            )
            ranked_items = sorted(
                items,
                key=lambda item: sum(
                    version
                    in (
                        item["link"]
                        + " "
                        + (item.get("title") or "")
                        + " "
                        + (item.get("snippet") or "")
                    )
                    for version in versions
                ),
                reverse=True,
            )
            if deep:
                ranked_items = diverse_sources(ranked_items, loaded)
            candidates = [
                item["link"] for item in ranked_items if item["link"] not in loaded
            ][:20 if deep else max(0, max_pages - len(docs))]
            if config.BYPASS_WEB_SEARCH_WEB_LOADER and not direct:
                candidates = []
            batch_size = max(0, max_pages - len(docs))
            docs.extend(await read_many(candidates[:batch_size]))
            # Replace blocked/empty pages with remaining candidates, within the same budget.
            if deep and len(docs) < max_pages and time.monotonic() < deadline:
                docs.extend(
                    await read_many(candidates[batch_size:][:max_pages - len(docs)])
                )
            loaded = {doc["metadata"]["source"] for doc in docs}
            snippet_count = 0
            for item in items:
                if len(docs) >= max_pages or (deep and snippet_count >= 2):
                    break
                if item["link"] not in loaded and item.get("snippet"):
                    docs.append(
                        {
                            "content": ("[Search result snippet; page not read]\n" if deep else "") + item["snippet"],
                            "metadata": {
                                "source": item["link"],
                                "title": item.get("title"),
                                "snippet_only": True,
                            },
                        }
                    )
                    loaded.add(item["link"])
                    snippet_count += 1

    question = form.question or " ".join(form.queries)
    per_page_limit = min(12000, (50000 if deep else 12000) // max(1, len(docs)))
    for doc in docs:
        doc["metadata"]["excerpt"] = len(doc["content"]) > per_page_limit
        doc["content"] = relevant_excerpt(doc["content"], question, per_page_limit)
    sources = [doc["metadata"]["source"] for doc in docs]
    return {
        "status": bool(docs),
        "collection_names": [],
        "filenames": sources,
        "items": items,
        "loaded_items": [item for item in items if item["link"] in sources],
        "docs": docs,
        "searched_count": len(items),
        "loaded_count": len(docs),
        "pages_read_count": sum(not doc["metadata"].get("snippet_only", False) for doc in docs),
        "snippet_count": sum(bool(doc["metadata"].get("snippet_only")) for doc in docs),
        "site_count": len({source_host(doc["metadata"]["source"]) for doc in docs if not doc["metadata"].get("snippet_only")}),
    }
