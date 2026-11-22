"""Opt-in installation; never invoked by an edit. See MAKER-MEDIA-LICENSES.md."""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from neveai.utils.video_edit_tool_assets import fetch, valid

SAM = "https://huggingface.co/facebook/sam2.1-hiera-small/resolve/ee5bba1d82bb8749febdf90f45e84b687142ba03/"
SAM_FILES = {
    "config.json":"97ff9f65b76d107acda4247885f0a5555d0048850ae3c5f97183df289aaecde9",
    "model.safetensors":"0a4067b11ce1e23d5229203f11c718a823060d15a4b23fa2372a7d4b77cbbc60",
    "preprocessor_config.json":"6ebf229ee259368ce4a8d4f2fe893a72b053023710853e257253939e601f583d",
    "processor_config.json":"f8a68e865cfad115c1c2763f3d93eca7b1c622da06da2a9273eb437fb2389b6d",
    "video_preprocessor_config.json":"9fccfe5f464ec38c2f236d0e6a68e95511c80c22132fc2fa4b9f7b65f24fad95",
}
PAINT = {
    "ProPainter.pth":"12c070c4b48f374c91d8a2a17851140b85c159621080989f9e191bbc18bd6591",
    "raft-things.pth":"fcfa4125d6418f4de95d84aec20a3c5f4e205101715a79f193243c186ac9a7e1",
    "recurrent_flow_completion.pth":"22939a1a7900da878dbe1ccd011d646b1bfb30b8290039d8ff0e0c2fefbfd283",
}
PACKAGES = ["imageio==2.37.0",
            "easydict==1.13","matplotlib==3.10.1","contourpy==1.3.2","cycler==0.12.1","fonttools==4.60.1",
            "kiwisolver==1.4.9","pyparsing==3.2.3"]


def provision(url, dest, digest):
    if valid(dest, digest):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as temp:
        path = Path(temp) / "download"
        fetch(url, path)
        if not valid(path, digest):
            raise ValueError("Invalid download: " + dest.name)
        path.replace(dest)


def upstream(dest, repo, revision, digest, folders):
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest) as temp:
        archive = Path(temp) / "project.zip"
        provision(f"https://codeload.github.com/{repo}/zip/{revision}", archive, digest)
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                parts = PurePosixPath(entry.filename).parts[1:]
                if not parts or ".." in parts or entry.is_dir():
                    continue
                if parts[0] not in folders and not parts[0].startswith("LICENSE"):
                    continue
                out = dest.joinpath(*parts)
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(entry) as src, out.open("wb") as target:
                    shutil.copyfileobj(src, target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--noncommercial", action="store_true", help="Install under the upstream S-Lab terms.")
    opts = parser.parse_args()
    if not opts.noncommercial:
        parser.error("Choose an optional toolset.")
    # Provision the shared Image 2 click selector at setup, not on a user's first edit.
    from neveai.routers.image_mode_selection import click_selector
    click_selector._load()
    root = Path(os.environ.get("DATA_DIR") or Path(__file__).parent / "data").resolve() / "cache/video_edit_tools"
    for name, digest in SAM_FILES.items():
        provision(SAM+name, root/"sam2"/name, digest)
    if opts.noncommercial:
        upstream(root/"propainter", "sczhou/ProPainter", "326782529a63d997cab80ab21439b92ed422b3d3",
                 "b04a9bb338f527a986629f65020ff581719b34ab9807a07d9d4440cf7bf625e4",
                 {"model","utils","core","inference_propainter.py"})
        for name, digest in PAINT.items():
            provision("https://github.com/sczhou/ProPainter/releases/download/v0.1.0/"+name,
                      root/"propainter/weights"/name,digest)
        subprocess.run([sys.executable,"-m","pip","install","--no-deps","--upgrade","--target",str(root/"packages"),*PACKAGES],check=True)
        (root/"mask-tools.ready").touch()


if __name__ == "__main__":
    main()
