"""Provision Neve Studio's transcription and clip-tool weights during setup."""
import argparse
import os
from pathlib import Path

from faster_whisper.utils import download_model
from huggingface_hub.errors import LocalEntryNotFoundError
from neveai.utils.video_edit_speakers import model_paths
from neveai.utils.video_edit_tool_assets import prepare_tools


def prepare():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Check the local assets without contacting the Hub.")
    check = parser.parse_args().check
    data = Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parent / "data").resolve()
    root = os.environ.get("WHISPER_MODEL_DIR") or str(data / "cache" / "whisper" / "models")
    prepare_tools(data / "cache" / "video_edit_tools", check)
    model_paths(Path(os.environ.get("CACHE_DIR") or data / "cache") / "video_edit_speakers", local_only=check)
    if check:
        download_model("turbo", cache_dir=root, local_files_only=True)
        return
    try:
        download_model("turbo", cache_dir=root, local_files_only=True)
    except LocalEntryNotFoundError:
        download_model("turbo", cache_dir=root)


if __name__ == "__main__":
    prepare()
