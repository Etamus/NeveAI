"""Prepare an isolated, pinned ComfyUI experiment without modifying existing runtimes."""
import concurrent.futures
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend/data/cache/image_moss_generation"


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    packages = TARGET / "runtime_packages"
    if not (packages / "comfy_kitchen/int8_decode.py").is_file():
        installer = ROOT / "backend/neveai/venv/Scripts/python.exe"
        subprocess.run([
            str(installer), "-m", "uv", "pip", "install", "--target", str(packages), "--no-deps",
            "comfy-kitchen==0.2.40", "comfy-aimdo==0.6.0",
        ], check=True, **({"creationflags": 0x08000000} if os.name == "nt" else {}))
    manifest_path = TARGET / "experiment_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        request = urllib.request.Request("https://api.github.com/repos/Comfy-Org/ComfyUI/commits/master", headers={"User-Agent": "NeveAI-MOSS-experiment"})
        revision = json.load(urllib.request.urlopen(request, timeout=60))["sha"]
        api = HfApi()
        repos = ["Comfy-Org/MOSS-Image", "chinoll/Moss-Image-Edit", "lodestones/MOSS-Image-SFT-8-steps-dmd"]
        manifest = {"comfy_commit": revision, "models": {repo: api.model_info(repo).sha for repo in repos}}
        manifest_path.write_text(json.dumps(manifest, indent=2))
    core = TARGET / "ComfyUI"
    if not (core / "main.py").is_file():
        archive = TARGET / "comfy-source.zip"
        urllib.request.urlretrieve(f"https://github.com/Comfy-Org/ComfyUI/archive/{manifest['comfy_commit']}.zip", archive)
        with zipfile.ZipFile(archive) as zipped:
            for item in zipped.infolist():
                relative = Path(*Path(item.filename).parts[1:])
                destination = (core / relative).resolve()
                if not destination.is_relative_to(core.resolve()):
                    raise ValueError("Invalid archive path")
                if item.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(zipped.read(item))
        archive.unlink()
    assets = [
        ("Comfy-Org/MOSS-Image", "diffusion_models/moss_image_sft_int8_convrot.safetensors", None),
        ("Comfy-Org/MOSS-Image", "text_encoders/qwen3.5_9b_int8_convrot.safetensors", None),
        ("Comfy-Org/MOSS-Image", "vae/flux2-vae_small.safetensors", None),
        ("chinoll/Moss-Image-Edit", "adapter_model.safetensors", "loras/moss_image_edit.safetensors"),
        ("lodestones/MOSS-Image-SFT-8-steps-dmd", "lora.safetensors", "loras/moss_image_dmd8.safetensors"),
    ]
    if "--bf16" in sys.argv:
        assets.append(("Comfy-Org/MOSS-Image", "diffusion_models/moss_image_sft_bf16.safetensors", None))

    def download(asset):
        repo, name, renamed = asset
        if renamed and (TARGET / "models" / renamed).is_file():
            return
        print(f"DOWNLOAD {repo}/{name}", flush=True)
        path = Path(hf_hub_download(repo, name, revision=manifest["models"][repo], local_dir=TARGET / "models"))
        if renamed:
            destination = TARGET / "models" / renamed
            destination.parent.mkdir(parents=True, exist_ok=True)
            path.replace(destination)
        print(f"READY {renamed or name}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download, assets))
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
