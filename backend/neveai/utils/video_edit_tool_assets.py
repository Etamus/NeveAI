"""Verified, installer-only downloads. Editing never contacts these origins."""
import hashlib
import os
import platform
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MDX = "UVR-MDX-NET-Inst_HQ_3.onnx"
REMASTER = "drunet_student.pth"
REMASTER_HASH = "21ee495de84de866d91af7c78e58cf8d1d68dc1d9016dd8e38f65f3a0559861e"
MDX_HASH = "317554b07fe1ea5279a77f2b1520a41ea4b93432560c4ffd08792c30fddf9adc"
RIFE = "rife-ncnn-vulkan-20221029-windows"
RIFE_FILES = {
    "rife-ncnn-vulkan.exe": "4b970319db2814c82b15fceed8193151560a676a9eb63f20d4877be77b98f44f",
    "vcomp140.dll": "54fe6b087528b33c2969143d811eb62f1bd49071d37de9db0745fc079764d698",
    "rife-v4.6/flownet.bin": "f334ed2260149ce0188a6dcf049844e8b0cdd912e01cbcfb63553157d2508958",
    "rife-v4.6/flownet.param": "28df14d57a225725ee5386f52eba422488450d37c9f40800ed4f62e8ba846692",
}


def windows_rife():
    return os.name == "nt" and platform.machine().lower() in ("amd64", "x86_64")


def valid(path, digest):
    if not path.is_file():
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == digest


def fetch(url, path):
    with urllib.request.urlopen(url, timeout=60) as response, path.open("wb") as out:
        shutil.copyfileobj(response, out)


def prepare_tools(root, check=False):
    root = Path(root)
    expected = {MDX: MDX_HASH, REMASTER: REMASTER_HASH, **(RIFE_FILES if windows_rife() else {})}
    missing = [name for name, digest in expected.items() if not valid(root / name, digest)]
    if not missing:
        return
    if check:
        raise FileNotFoundError("Missing or invalid Maker tool: " + missing[0])
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as scratch:
        tmp = Path(scratch)
        if REMASTER in missing:
            fetch("https://huggingface.co/seantempesta/remaster-drunet/resolve/"
                  "4545e2ec12450f676f5691d990ee591a189741ca/" + REMASTER, tmp / REMASTER)
        if MDX in missing:
            fetch("https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/" + MDX, tmp / MDX)
        if any(name in RIFE_FILES for name in missing):
            archive = tmp / "rife.zip"
            fetch(f"https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/{RIFE}.zip", archive)
            if not valid(archive, "d8e4d772d26cd8006ef0ad0bc82eb191b53c68677d1ae2f42506d74cbbbea606"):
                raise ValueError("Invalid RIFE archive.")
            with zipfile.ZipFile(archive) as z:
                for name in missing:
                    if name not in RIFE_FILES:
                        continue
                    (tmp / name).parent.mkdir(exist_ok=True)
                    with z.open(RIFE + "/" + name) as src, (tmp / name).open("wb") as dst:
                        shutil.copyfileobj(src, dst)
        for name in missing:
            if not valid(tmp / name, expected[name]):
                raise ValueError("Invalid Maker tool: " + name)
        for name in missing:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (tmp / name).replace(root / name)
