"""Stage verified upstream runtime assets without changing active runtimes."""

import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "logs/runtime-upgrade-20261029"
COMFY_COMMIT = "426f5eea52a7ece1dd599fff4cb6cd1f352ddd24"
XL_REVISION = "d4a0b288b83ebb7e25a8c0b32c573c22e134e8ee"


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Neve-runtime-upgrade"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or (expected and sha256(target) != expected):
        partial = target.with_suffix(target.suffix + ".partial")
        request = urllib.request.Request(url, headers={"User-Agent": "Neve-runtime-upgrade"})
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, 4 * 1024 * 1024)
        if expected and sha256(partial) != expected:
            raise RuntimeError(f"Checksum mismatch: {target.name}")
        partial.replace(target)
    print(f"Verified/staged: {target.name}", flush=True)


def extract(archive_path, destination):
    if destination.exists():
        return
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            resolved = (destination / entry.filename).resolve()
            if not resolved.is_relative_to(destination.resolve()):
                raise RuntimeError("Unsafe archive member")
        archive.extractall(destination)


def main():
    STAGE.mkdir(parents=True, exist_ok=True)
    archive = STAGE / "comfy-0.43.0.zip"
    download(f"https://github.com/Comfy-Org/ComfyUI/archive/{COMFY_COMMIT}.zip", archive)
    extract(archive, STAGE / "comfy-source")
    release = get_json("https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11960")
    selected = []
    for name in ("llama-b11960-bin-win-cuda-13.4-x64.zip", "cudart-llama-bin-win-cuda-13.4-x64.zip"):
        asset = next(item for item in release["assets"] if item["name"] == name)
        download(asset["browser_download_url"], STAGE / name, asset["digest"].removeprefix("sha256:"))
        extract(STAGE / name, STAGE / name.removesuffix(".zip"))
        selected.append({key: asset[key] for key in ("name", "size", "digest", "browser_download_url")})
    (STAGE / "upstream.json").write_text(json.dumps({
        "comfy_commit": COMFY_COMMIT, "llama": selected, "xl_revision": XL_REVISION,
    }, indent=2), encoding="utf-8")
    print("Downloading pinned ACE-Step XL weights", flush=True)
    from huggingface_hub import snapshot_download

    snapshot_download(
        "ACE-Step/acestep-v15-xl-turbo", revision=XL_REVISION,
        local_dir=ROOT / "backend/data/cache/music_generation/ACE-Step-1.5/checkpoints/acestep-v15-xl-turbo",
        max_workers=2,
    )
    print("All assets staged", flush=True)


if __name__ == "__main__":
    main()
