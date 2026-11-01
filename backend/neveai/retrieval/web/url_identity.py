"""Resource identity for URL-first reading, independent of application state."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import re

TRACKING = {"fbclid", "gclid", "dclid", "msclkid", "igshid"}
REDDIT_CHALLENGE = {"solution", "js_challenge", "jsc_token", "jsc_orig_r"}
SECRET_QUERY = {"token", "access_token", "auth", "authorization", "signature", "key", "api_key", "password", "session"}


def canonical_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    reddit = host == "reddit.com" or host.endswith(".reddit.com")
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith(("utm_", "__cf_chl_")) and key.lower() not in TRACKING
             and not (reddit and key.lower() in REDDIT_CHALLENGE)]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def reddit_resource(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if host != "reddit.com" and not host.endswith(".reddit.com"):
        return None
    match = re.match(r"/(?:r/[^/]+/)?comments/([a-z0-9]+)(?:/[^/]+)?(?:/([a-z0-9]+))?/?$", parsed.path, re.I)
    if match:
        return match[1].lower(), (match[2] or "").lower()
    return None


def resource_identity(url):
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid source identity")
    reddit = reddit_resource(url)
    if reddit:
        return ("reddit-post", *reddit)
    parsed = urlsplit(canonical_url(url))
    host = (parsed.hostname or "").lower().removeprefix("www.")
    port = parsed.port
    if port == (443 if parsed.scheme == "https" else 80):
        port = None
    return (host, port, parsed.path.rstrip("/") or "/", tuple(sorted(parse_qsl(parsed.query, keep_blank_values=True))))


def matches_requested_resource(url, requested):
    try:
        return any(resource_identity(url) == resource_identity(original) for original in requested)
    except (TypeError, ValueError):
        return False


def searchable_url(url):
    parsed = urlsplit(canonical_url(url))
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if key.lower() not in SECRET_QUERY and not key.lower().startswith("x-amz-")]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def reddit_feed_url(url):
    resource = reddit_resource(url)
    if resource:
        post, comment = resource
        path = f"/comments/{post}/_/{comment}/.rss" if comment else f"/comments/{post}/.rss"
        return "https://www.reddit.com" + path
    return None


def wants_additional_sources(question):
    text = re.sub(r"https?://\S+", " ", question or "", flags=re.I).casefold()
    return bool(re.search(
        r"\b(?:compare|comparar|comparison|versus|vs|verifique|confira|verificar|verify|fact.check|"
        r"alternativas?|alternatives?|outras fontes|other sources|al[e\u00e9]m do link|al[e\u00e9]m da p[a\u00e1]gina|"
        r"beyond (?:this|the) (?:link|page)|pesquise tamb[e\u00e9]m|also search)\b", text
    ))


def extract_reddit_html(text, requested):
    from bs4 import BeautifulSoup

    resource = reddit_resource(requested)
    if not resource:
        return None
    soup = BeautifulSoup(text, "html.parser")
    target = "t1_" + resource[1] if resource[1] else "t3_" + resource[0]
    post = soup.find(id=target) or soup.find(attrs={"thingid": target}) or soup.find(attrs={"data-fullname": target})
    if post is None:
        return None
    body = post.select_one('[slot="text-body"], [slot="comment"], [slot="comment-body"], .usertext-body .md')
    if body is None:
        return None
    title = post.get("post-title") or (soup.title.get_text(" ", strip=True) if soup.title else requested)
    content = body.get_text("\n", strip=True)
    if not content:
        return None
    return {"content": (title + "\n\n" + content)[:80000], "metadata": {
        "source": requested, "title": title, "link": requested, "resource_id": target,
        "extraction_method": "post_body",
    }}


def extract_reddit_feed(data, requested):
    from lxml import etree
    from bs4 import BeautifulSoup

    resource = reddit_resource(requested)
    if not resource:
        return None
    try:
        root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as error:
        raise ValueError("Unreadable public feed") from error
    if root.getroottree().docinfo.doctype:
        raise ValueError("External feed declarations are not supported")
    namespace = {"a": "http://www.w3.org/2005/Atom"}
    target = "t1_" + resource[1] if resource[1] else "t3_" + resource[0]
    for entry in root.findall("a:entry", namespace):
        if entry.findtext("a:id", namespaces=namespace) != target:
            continue
        body = BeautifulSoup(entry.findtext("a:content", default="", namespaces=namespace), "html.parser")
        content = body.select_one(".md") or body
        title = entry.findtext("a:title", default="", namespaces=namespace)
        text = content.get_text("\n", strip=True)
        if text:
            return {"content": (title + "\n\n" + text)[:80000], "metadata": {
                "source": requested, "link": requested, "title": title,
                "extraction_method": "public_feed", "resource_id": target,
            }}
    return None
