"""Isolated image-only study; does not modify production settings or chats."""
import asyncio
import base64
import json
import sys
import time
import os
import subprocess
import psutil
from urllib.request import urlopen
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.routers.image_h3_generation import neve_image_3_runtime as h3
import neveai.routers.image_h3_generation as h3_module
from neveai.routers.image_fast_generation import neve_image_2s_runtime as qwen

OUT = ROOT / "logs" / "h3-study-20261113"
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    original = h3.build_workflow
    results = []
    suffix = "-extra" if "--extra" in sys.argv else ""
    user_case = "--user" in sys.argv or "--seeds" in sys.argv
    if user_case:
        suffix = "-user"
    if "--seeds" in sys.argv:
        suffix = "-seeds"
    source = ROOT / "logs/h3-images/h3-portrait-pt.png"
    if user_case:
        source = OUT / "user-source.png"
        source.write_bytes(urlopen("http://127.0.0.1:8080/api/v1/files/b176a807-711e-4628-9ae4-ff79ecdee2cd/content").read())
        for label, identifier in [("original-h3", "c5c94b4e-df93-43d3-8d6a-201369641c51"),
                                  ("original-qwen", "d76fa410-7397-41f7-b5bf-a10deb418e3f"),
                                  ("original-image26", "2d58a439-8777-4840-a6aa-2270eb4545a6")]:
            target = OUT / (label + ".png")
            target.write_bytes(urlopen(f"http://127.0.0.1:8080/api/v1/files/{identifier}/content").read())
            with Image.open(target) as im:
                im.thumbnail((640, 640), Image.Resampling.LANCZOS)
                im.save(OUT / (label + "-preview.png"))
    ref = "data:image/png;base64," + base64.b64encode(source.read_bytes()).decode()
    with Image.open(source) as im:
        im.thumbnail((640, 640), Image.Resampling.LANCZOS)
        im.save(OUT / ("user-source-preview.png" if user_case else "source-preview.png"))
    pt = "Mude somente o cabelo da mulher da direita para azul. Preserve os rostos, roupas e o fundo."
    en = "Change only the right woman's pink hair to blue. Keep her green shirt unchanged. Preserve both women's faces, poses, all clothing and the entire background."
    remove = "Remova a mulher da esquerda. Preserve a mulher da direita exatamente como esta, incluindo cabelo rosa e camisa verde. Preencha naturalmente o banco e o jardim onde estava a outra mulher."
    cases = [
        ("h3-pt-4mp", h3, pt, 2048),
        ("h3-en-4mp", h3, en, 2048),
        ("h3-en-8mp", h3, en, 2880),
        ("qwen-pt", qwen, pt, None),
        ("h3-remove", h3, remove, 2048),
        ("qwen-remove", qwen, remove, None),
    ]
    if suffix == "-extra":
        cases = [("h3-en-8mp-corrected", h3, en, 2880),
                 ("h3-en-16mp", h3, en, 4096)]
    if user_case:
        cases = [("h3-user-pt-4mp", h3, "Troque a cor do cabelo dela por vermelho", 4),
                 ("h3-user-en-4mp", h3, "Edit <Picture 1>. Change only her hair color to red. Keep the original eye color exactly unchanged. Preserve the face, expression, skin, clothing, background and illustration style. Do not recolor the irises or any other object.", 4),
                 ("h3-user-pt-8mp", h3, "Troque a cor do cabelo dela por vermelho", 8)]
    if "--seeds" in sys.argv:
        base_cases = cases[:2]
        cases = [(f"{name}-seed{seed}", rt, prompt, mp)
                 for seed in (42, 43) for name, rt, prompt, mp in base_cases]
    original_canvas = h3_module.canvas_size
    async def progress(value):
        pass
    try:
        for name, runtime, prompt, side in cases:
            case_seed = int(name.rsplit("seed", 1)[1]) if "-seed" in name else 742319
            if runtime is h3:
                if user_case:
                    h3_module.canvas_size = lambda *args, side=side, **kwargs: original_canvas(*args, megapixels=side)
                else:
                    h3_module.canvas_size = lambda *args, side=side, **kwargs: (side, side)
                def workflow(p, w, h, refs, seed, side=side):
                    return original(p, w if user_case else side, h if user_case else side, refs, case_seed)
                h3.build_workflow = workflow
            start = time.perf_counter()
            print("START", name, flush=True)
            record = {"case": name, "prompt": prompt, "seed_h3": case_seed if runtime is h3 else None}
            async def monitor():
                while True:
                    free = psutil.virtual_memory().available / 1024**3
                    record["min_ram_free_gib"] = min(record.get("min_ram_free_gib", free), free)
                    process = await asyncio.create_subprocess_exec(
                        "nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
                        stdout=asyncio.subprocess.PIPE,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    output, _ = await process.communicate()
                    used = int(output.strip().splitlines()[0])
                    record["peak_vram_mib"] = max(record.get("peak_vram_mib", 0), used)
                    await asyncio.sleep(2)
            monitor_task = asyncio.create_task(monitor())
            try:
                uri = await runtime.run(prompt, "1:1", [ref], None, progress)
                path = OUT / (name + ".png")
                path.write_bytes(base64.b64decode(uri.split(",", 1)[1]))
                with Image.open(path) as im:
                    record["size"] = im.size
                    im.thumbnail((640, 640), Image.Resampling.LANCZOS)
                    im.save(OUT / (name + "-preview.png"))
            except Exception as exc:
                record["error"] = str(exc)
                record["worker_log"] = runtime._log_tail[-25:]
            finally:
                monitor_task.cancel()
                await asyncio.gather(monitor_task, return_exceptions=True)
            record["seconds"] = round(time.perf_counter() - start, 3)
            results.append(record)
            (OUT / ("results" + suffix + ".json")).write_text(json.dumps(results, indent=2), encoding="utf8")
            print(json.dumps(record), flush=True)
    finally:
        h3.build_workflow = original
        h3_module.canvas_size = original_canvas


asyncio.run(main())
