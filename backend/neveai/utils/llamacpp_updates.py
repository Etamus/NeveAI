import asyncio
import re
from urllib.parse import unquote


WINDOWS_BACKENDS = (
    "cpu", "cuda-12.4", "cuda-13.4", "cuda-13.3",
    "cuda-cu12.4", "cuda-cu13.4", "cuda-cu13.3", "vulkan",
)


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
        if match and match[1].lower() in WINDOWS_BACKENDS and compatible_backend(backend, match[1].lower()):
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

    # The feed alone cannot prove that a package for this backend was published.
    try:
        async with asyncio.timeout(8):
            async with session.get("https://github.com/ggml-org/llama.cpp/releases.atom", ssl=ssl) as response:
                response.raise_for_status()
                feed = await response.text()
            candidates = [value for value in WINDOWS_BACKENDS if compatible_backend(backend, value)]
            tags = dict.fromkeys(unquote(value).strip() for value in re.findall(r'/releases/tag/([^"<]+)', feed))
            for tag in list(tags)[:5]:
                if not re.fullmatch(r"b\d+", tag, re.I):
                    continue
                for candidate in candidates:
                    url = f"https://github.com/ggml-org/llama.cpp/releases/download/{tag}/llama-{tag}-bin-win-{candidate}-x64.zip"
                    try:
                        async with session.head(url, allow_redirects=True, ssl=ssl) as response:
                            if 200 <= response.status < 300:
                                return tag
                    except Exception:
                        continue
    except Exception:
        pass
    raise api_error
