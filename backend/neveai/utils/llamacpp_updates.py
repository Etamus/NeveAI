import asyncio
from html.parser import HTMLParser
import re
from urllib.parse import unquote, urlsplit


WINDOWS_BACKENDS = (
    "cpu", "cuda-12.4", "cuda-13.4", "cuda-13.3",
    "cuda-cu12.4", "cuda-cu13.4", "cuda-cu13.3", "vulkan",
)


class _ReleaseLinks(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def _release_tags(html: str) -> list[str]:
    prefix = "/ggml-org/llama.cpp/releases/tag/"
    tags = []
    for link in _ReleaseLinks(html).links:
        path = unquote(urlsplit(link).path)
        if path.startswith(prefix):
            tag = path[len(prefix):]
            if re.fullmatch(r"b\d+", tag, re.I):
                tags.append(tag)
    return list(dict.fromkeys(tags))


def _release_from_assets(tag: str, html: str) -> dict:
    prefix = f"/ggml-org/llama.cpp/releases/download/{tag}/"
    assets = []
    for link in _ReleaseLinks(html).links:
        path = unquote(urlsplit(link).path)
        if path.startswith(prefix):
            assets.append({"name": path[len(prefix):]})
    return {"tag_name": tag, "assets": assets}


def installed_backend(info: dict) -> str:
    match = re.search(r"-bin-win-(.+)-x64\.zip$", info.get("asset", ""), re.I)
    if match:
        return match[1].lower()
    backend = info.get("backend", "").strip().lower()
    match = re.search(r"cuda(?:-cu)?[- ]?(\d+)", backend)
    if match:
        return f"cuda-{match[1]}"
    return backend


def compatible_backend(requested: str, available: str) -> bool:
    if not requested or requested == available:
        return True
    requested_cuda = re.fullmatch(r"cuda(?:-cu)?-?(\d+)(?:\.\d+)?", requested)
    available_cuda = re.fullmatch(r"cuda(?:-cu)?-?(\d+)(?:\.\d+)?", available)
    return bool(requested_cuda and available_cuda and requested_cuda[1] == available_cuda[1])


def compatible_release(release: dict, backend: str = "") -> bool:
    if not isinstance(release, dict) or release.get("draft"):
        return False
    tag = str(release.get("tag_name") or "").strip()
    if not re.fullmatch(r"b\d+", tag, re.I):
        return False
    pattern = re.compile(rf"^llama-{re.escape(tag)}-bin-win-(.+)-x64\.zip$", re.I)
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        match = pattern.fullmatch(str(asset.get("name") or "").strip())
        available = match[1].lower() if match else ""
        supported = available in {"cpu", "vulkan"} or re.fullmatch(r"cuda(?:-cu)?-?(?:12|13)(?:\.\d+)?", available)
        if match and supported and compatible_backend(backend, available):
            return True
    return False


async def latest_compatible_release_tag(session, backend: str = "", ssl=True) -> str:
    api_error = None
    try:
        async with session.get(
            "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30", ssl=ssl
        ) as response:
            response.raise_for_status()
            releases = await response.json()
            for release in releases if isinstance(releases, list) else []:
                if compatible_release(release, backend):
                    return release["tag_name"].strip()
            raise RuntimeError("No compatible Windows llama.cpp release found")
    except Exception as error:
        api_error = error

    # The Atom feed lists too few releases and guessed package names miss older
    # compatible CUDA builds. Read published manifests, with the same rules as API.
    try:
        async with asyncio.timeout(8):
            async def read_html(path):
                try:
                    async with session.get(f"https://github.com/ggml-org/llama.cpp/{path}", ssl=ssl) as response:
                        response.raise_for_status()
                        return await response.text()
                except Exception:
                    return ""

            pages = await asyncio.gather(*(read_html(f"releases?page={page}") for page in range(1, 4)))
            tags = sorted({tag for html in pages for tag in _release_tags(html)},
                          key=lambda tag: int(tag[1:]), reverse=True)[:30]
            for offset in range(0, len(tags), 4):
                batch = tags[offset:offset + 4]
                manifests = await asyncio.gather(*(read_html(f"releases/expanded_assets/{tag}") for tag in batch))
                for tag, html in zip(batch, manifests):
                    if compatible_release(_release_from_assets(tag, html), backend):
                        return tag
    except Exception:
        pass
    raise api_error
