"""Verify pinned weights and record installed artifacts and benchmark summaries."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs/runtime-upgrade-20261029"
WEIGHTS = {
    "model-00001-of-00004.safetensors": "e54a8413c981797312f53d512dec9944023d03f42f0740cbe86f62582cc27bdc",
    "model-00002-of-00004.safetensors": "b45f788b6dc9f15957cfa3d9b403f25f3f64c5211ecaf18dda45b67ea6470664",
    "model-00003-of-00004.safetensors": "a4f6bd572eab79cf5f3e4678796f904c6d6c33680a3e6ed09034d6de7cabea4d",
    "model-00004-of-00004.safetensors": "a868b05493c73808408f58b33a903371bb2846b53c8b19bd7476991bc8837259",
}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    result = {"xl_weights": {}, "comfy": {}, "llama": {}}
    for name, expected in WEIGHTS.items():
        path = ROOT / "backend/data/cache/music_generation/ACE-Step-1.5/checkpoints/acestep-v15-xl-turbo" / name
        actual = sha(path)
        assert actual == expected, name
        result["xl_weights"][name] = dict(bytes=path.stat().st_size, sha256=actual)
        print("Verified " + name, flush=True)
    for runtime in ("image_fast_generation", "video_generation"):
        source = ROOT / "backend/data/cache" / runtime / "ComfyUI"
        commit = (source / ".neve-comfy-commit").read_text().strip()
        assert commit == "426f5eea52a7ece1dd599fff4cb6cd1f352ddd24"
        result["comfy"][runtime] = dict(commit=commit, version_source=(source / "comfyui_version.py").read_text().strip(),
                                      backups=[str(path.relative_to(ROOT)) for path in source.parent.glob("ComfyUI.previous-*")])
    active = ROOT / "llamacpp-server/bin"
    candidate = REPORT / "llama-b11960-bin-win-cuda-13.4-x64"
    for path in active.iterdir():
        if path.is_file():
            digest = sha(path)
            if candidate.exists():
                assert digest == sha(candidate / path.name), path.name
            result["llama"][path.name] = digest
    version = subprocess.run([str(active / "llama-server.exe"), "--version"], capture_output=True, text=True, check=True)
    result["llama_version"] = (version.stdout + version.stderr).strip()
    result["music_software"] = "ACE-Step v0.1.8; XL Turbo pinned d4a0b288b83ebb7e25a8c0b32c573c22e134e8ee"
    metrics = []
    for path in sorted(REPORT.glob("*-telemetry.json")):
        value = json.loads(path.read_text())
        samples = value["samples"]
        metrics.append(dict(name=path.name.removesuffix("-telemetry.json"), exit_code=value["exit_code"], seconds=value["seconds"],
            temperature_peak_c=max((s["temperature_c"] for s in samples), default=0),
            vram_peak_mib=max((s["vram_mib"] for s in samples), default=0),
            ram_peak_gib=max((s["ram_used_gib"] for s in samples), default=0)))
    result["telemetry_summary"] = metrics
    (REPORT / "verified-installation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(dict(llama_version=result["llama_version"], telemetry=metrics), indent=2), flush=True)


if __name__ == "__main__":
    main()
