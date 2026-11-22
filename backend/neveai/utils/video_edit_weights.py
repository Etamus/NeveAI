"""Pinned Neve Studio assets, shared by provisioning and the offline runtime."""
from pathlib import Path

REPO = "Qwen/Qwen3-VL-8B-Instruct-GGUF"
REVISION = "f982a07559d4a2f6c8744d840bf6fccab30eea96"
MODEL_NAME = "Neve Studio"
WEIGHTS = (
    ("Qwen3VL-8B-Instruct-Q4_K_M.gguf", 5027784800, "67d1659bfe71b89d50b45a4ad1a9e5b997e5bb16ce5da66a6a6167abd569e9e2"),
    ("mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf", 752289728, "c6ba85508d82f42590e6eb77d5340369ab6fecf107a7561d809523d8aa5f3bfd"),
)


def weights_dir(data_dir: Path):
    return data_dir / "neve_maker" / "vision" / REVISION


def local_weights(directory: Path):
    paths = []
    for name, size, _ in WEIGHTS:
        path = directory / name
        if not path.is_file() or path.stat().st_size != size:
            raise FileNotFoundError(name)
        paths.append(path)
    return tuple(paths)
