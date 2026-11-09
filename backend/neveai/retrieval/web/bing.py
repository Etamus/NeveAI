"""Small HTML fallback when the configured free search providers return no data."""
import base64
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
import requests


def parse_bing_results(html: str, count: int) -> list[dict]:
    if count <= 0:
        return []
    soup = BeautifulSoup(html, "html.parser")
    results, seen = [], set()
    for item in soup.select("li.b_algo"):
        anchor = item.select_one("h2 a[href]")
        if not anchor:
            continue
        href = anchor.get("href", "")
        try:
            parsed = urlsplit(href)
        except ValueError:
            continue
        if parsed.hostname in {"bing.com", "www.bing.com"} and parsed.path == "/ck/a":
            encoded = parse_qs(parsed.query).get("u", [""])[0]
            try:
                if not encoded.startswith("a1"):
                    continue
                encoded = encoded[2:]
                href = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
                parsed = urlsplit(href)
            except (ValueError, UnicodeError):
                continue
        title = anchor.get_text(" ", strip=True)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or href in seen or not title:
            continue
        if parsed.hostname in {"bing.com", "www.bing.com"}:
            continue
        snippet = item.select_one(".b_caption p")
        results.append({"href": href, "title": title,
                        "body": snippet.get_text(" ", strip=True) if snippet else ""})
        seen.add(href)
        if len(results) >= count:
            break
    return results


def search_bing_fallback(query: str, count: int, timeout: float) -> list[dict]:
    response = requests.get("https://www.bing.com/search",
                            params={"q": query, "setlang": "en-US", "cc": "us"}, timeout=timeout)
    response.raise_for_status()
    return parse_bing_results(response.text, count)
