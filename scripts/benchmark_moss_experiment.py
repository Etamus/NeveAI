"""Controlled local image comparison; no writes to user chats or the library."""
import argparse
import asyncio
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from PIL import Image
import httpx
from neveai.routers.image_moss_generation import neve_image_3_runtime

REPORT = ROOT / "logs/moss-study-20261024"
REPORT.mkdir(parents=True, exist_ok=True)
FIXTURES = ROOT / "logs/image2-modes"
CASES = [
    ("jacket", "Change only the blue jacket to a green jacket. Preserve the same man's face, body proportions, pose, white shirt, trousers, shoes and gray studio background.", ["main"]),
    ("background", "Replace the entire gray studio background with the interior of a medieval stone dungeon with iron-barred cells and warm torch light. Keep the same adult man, face, blue jacket, pose and normal full-body proportions.", ["main"]),
    ("two_refs", "Dress the man in image 1 with the red coat from image 2. Keep the man from image 1, his face, body proportions, pose, trousers, shoes, and the gray background. Do not replace him with the woman from image 2.", ["main", "reference"]),
    ("text", "Add a small rectangular white name badge to the blue jacket. The badge must read NEVE in clear black capital letters. Keep everything else unchanged, including the man's face and the gray background.", ["main"]),
    ("portuguese", "Troque somente a jaqueta azul por uma jaqueta verde. Mantenha o mesmo homem, rosto, pose, calças, sapatos e fundo cinza.", ["main"]),
    ("four_refs", "Dress the man in image 1 with the red coat from image 2. Images 3 and 4 repeat these references. Preserve the man, face, trousers and studio background from image 1.", ["main", "reference", "main", "reference"]),
    ("generation", "A realistic product photograph of a red ceramic mug beside a closed black notebook and a silver pen, on a dark green desk. Clear natural daylight, precise material textures, no text.", []),
]
PROFILES = {
    "fast8_int8": {"steps": 8, "cfg": 1., "turbo": 1.},
    "fast4_int8": {"steps": 4, "cfg": 1., "turbo": 1.},
    "edit12_int8": {"steps": 12, "cfg": 3., "turbo": 0.},
    "edit30_int8": {"steps": 30, "cfg": 4., "turbo": 0.},
    "fast8_bf16": {"steps": 8, "cfg": 1., "turbo": 1., "bf16": True},
    "fast8_ref768": {"steps": 8, "cfg": 1., "turbo": 1., "reference_edge": 768},
    "fast8_ref1024": {"steps": 8, "cfg": 1., "turbo": 1., "reference_edge": 1024},
    "edit12_matched": {"steps": 12, "cfg": 3., "turbo": 0., "reference_edge": 1024, "output_pixels": 1152*1152},
    "fast8_matched": {"steps": 8, "cfg": 1., "turbo": 1., "reference_edge": 1024, "output_pixels": 1152*1152},
}


async def telemetry(samples, stop, base, cancel=None):
    while not stop.is_set():
        process = await asyncio.create_subprocess_exec(
            "nvidia-smi", "--query-gpu=temperature.gpu,memory.used,power.draw,utilization.gpu", "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            **({"creationflags": 0x08000000} if os.name == "nt" else {}),
        )
        output, _ = await process.communicate()
        try:
            temperature, memory, power, utilization = map(float, output.decode().strip().split(","))
            samples.append({"time": time.monotonic(), "temperature": temperature, "vram_mib": memory, "power_w": power, "gpu_percent": utilization})
            if temperature >= 78:
                if cancel:
                    await cancel()
                async with httpx.AsyncClient(timeout=3) as client:
                    await client.post(base + "/interrupt")
                raise RuntimeError("Benchmark interrupted at the experiment's 78C thermal ceiling")
        except ValueError:
            pass
        try:
            await asyncio.wait_for(stop.wait(), 1)
        except asyncio.TimeoutError:
            pass


async def progress(value):
    pass


async def main(args):
    results_path = REPORT / "measurements.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    base = "http://127.0.0.1:8193"
    raw = {name: (FIXTURES / (name + ".png")).read_bytes() for name in ["main", "reference"]}
    profiles = args.profiles.split(",")
    for name in profiles:
        for case, prompt, refs in CASES:
            if args.cases and case not in args.cases.split(","):
                continue
            key = name + ("_cold" if args.cold else "") + "_" + case
            if any(item["key"] == key and item.get("ok") for item in results) and not args.repeat:
                continue
            print("START " + key, flush=True)
            samples, details = [], {}
            stop = asyncio.Event()
            runtime = None
            if name.startswith("qwen"):
                from neveai.routers.image_fast_generation import neve_image_2s_runtime
                from neveai.routers.image_quality_generation import neve_image_21_runtime
                runtime = neve_image_2s_runtime if name == "qwen2" else neve_image_21_runtime
            elif args.cold:
                runtime = neve_image_3_runtime
            monitor = asyncio.create_task(telemetry(samples, stop, base, runtime.cancel if runtime else None))
            started = time.monotonic()
            try:
                if name.startswith("qwen"):
                    with patch("neveai.routers.stable_diffusion._read_image_reference_bytes", side_effect=lambda ref, user: raw[ref]), \
                         patch("neveai.routers.image_quality_generation._read_image_reference_bytes", side_effect=lambda ref, user: raw[ref]):
                        if name == "qwen26":
                            data = await runtime.run(prompt, "3:4", refs, None, progress, details=details)
                        else:
                            data = await runtime.run(prompt, "3:4", refs, None, progress)
                else:
                    active_base = await runtime._start() if args.cold else base
                    data = await neve_image_3_runtime.execute(active_base, prompt, "3:4", [raw[ref] for ref in refs], progress, seed=42, profile=PROFILES[name], details=details)
                    if args.cold:
                        await runtime._stop()
                path = REPORT / (key + ".png")
                path.write_bytes(base64.b64decode(data.split(",", 1)[1]))
                with Image.open(path) as image:
                    size = image.size
                result = {"key": key, "ok": True, "seconds": round(time.monotonic()-started, 3), "dimensions": size, "details": details}
            except Exception as error:
                import traceback
                traceback.print_exc()
                result = {"key": key, "ok": False, "seconds": round(time.monotonic()-started, 3), "error": str(error)}
            finally:
                if args.cold and runtime:
                    await runtime._stop()
                stop.set()
                await monitor
            result.update({"temperature_peak_c": max((s["temperature"] for s in samples), default=None), "vram_peak_mib": max((s["vram_mib"] for s in samples), default=None), "gpu_average_w": sum(s["power_w"] for s in samples)/max(1,len(samples))})
            results.append(result)
            results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
            (REPORT / (key + "-telemetry.json")).write_text(json.dumps(samples), encoding="utf-8")
            print(json.dumps(result), flush=True)
            if not result["ok"]:
                raise RuntimeError(result["error"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", default="fast8_int8")
    parser.add_argument("--cases", default="")
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--cold", action="store_true")
    asyncio.run(main(parser.parse_args()))
