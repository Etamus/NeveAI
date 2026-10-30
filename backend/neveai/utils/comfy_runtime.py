"""Pinned ComfyUI source updates; model/runtime directories remain independent."""
import shutil
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

COMFY_COMMIT = "426f5eea52a7ece1dd599fff4cb6cd1f352ddd24"
SOURCE_MARKER = ".neve-comfy-commit"


def install_comfy_source(destination: Path, commit: str = COMFY_COMMIT) -> None:
    destination = destination.resolve()
    marker = destination / SOURCE_MARKER
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == commit and (destination / "main.py").is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="comfy-update-", dir=destination.parent) as temporary:
        root = Path(temporary)
        archive_path = root / "source.zip"
        request = urllib.request.Request(
            f"https://github.com/Comfy-Org/ComfyUI/archive/{commit}.zip",
            headers={"User-Agent": "NeveAI/1.0"},
        )
        with urllib.request.urlopen(request, timeout=120) as response, archive_path.open("wb") as output:
            shutil.copyfileobj(response, output)
        extracted = root / "source"
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if not (extracted / member.filename).resolve().is_relative_to(extracted.resolve()):
                    raise RuntimeError("Caminho invalido no pacote ComfyUI")
            archive.extractall(extracted)
        sources = [path for path in extracted.iterdir() if path.is_dir()]
        if len(sources) != 1 or not all((sources[0] / name).is_file() for name in ("main.py", "requirements.txt")):
            raise RuntimeError("Pacote ComfyUI incompleto")
        source = sources[0]
        (source / SOURCE_MARKER).write_text(commit, encoding="utf-8")
        backup = destination.with_name(destination.name + f".previous-{time.time_ns()}")
        preserved = []
        had_previous = destination.exists()
        if had_previous:
            destination.rename(backup)
        try:
            for name in ("models", "custom_nodes", "input", "output", "temp", "user", "extra_model_paths.yaml"):
                previous = backup / name
                if not previous.exists():
                    continue
                replacement = source / name
                if replacement.is_dir():
                    shutil.rmtree(replacement)
                elif replacement.exists():
                    replacement.unlink()
                previous.rename(replacement)
                preserved.append(name)
            source.rename(destination)
        except BaseException:
            for name in reversed(preserved):
                (source / name).rename(backup / name)
            if had_previous:
                backup.rename(destination)
            raise
