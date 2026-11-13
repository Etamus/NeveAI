"""GPU comparison on synthetic images. Never edits or saves user chats."""
import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import sys
import time
import subprocess
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from neveai.routers.image_h3_generation import neve_image_3_runtime as h3

OUT = Path(__file__).resolve().parents[1] / "logs" / "h3-images"
OUT.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO)


async def main():
    results = []
    extended = "--extended" in sys.argv
    preservation = "--preservation" in sys.argv
    async def run(name, runtime, prompt, refs):
        start = time.perf_counter()
        print("START", name, prompt, flush=True)
        last = -1
        peak_vram = 0
        min_ram_free = psutil.virtual_memory().available
        async def monitor():
            nonlocal peak_vram, min_ram_free
            while True:
                min_ram_free = min(min_ram_free, psutil.virtual_memory().available)
                process = await asyncio.create_subprocess_exec("nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
                    stdout=asyncio.subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                stdout, _ = await process.communicate()
                peak_vram = max(peak_vram, int(stdout.strip().splitlines()[0]))
                await asyncio.sleep(2)
        monitor_task = asyncio.create_task(monitor()) if extended else None
        async def progress(value):
            nonlocal last
            if value != last:
                print(name, "progress", value, "seconds", round(time.perf_counter() - start, 2), flush=True)
                last = value
        try:
            uri = await runtime.run(prompt, "1:1", refs, None, progress)
            path = OUT / (name + ".png")
            path.write_bytes(base64.b64decode(uri.split(",", 1)[1]))
            record = {"name": name, "prompt": prompt, "seconds": round(time.perf_counter()-start, 3), "image": str(path),
                      **({"peak_vram_mib_sampled": peak_vram, "min_system_ram_free_gib_sampled": round(min_ram_free/1024**3, 2)} if extended else {})}
            results.append(record)
            print("RESULT", json.dumps(record), flush=True)
            return uri
        except Exception as exc:
            record = {"name": name, "seconds": round(time.perf_counter()-start, 3), "error": str(exc), "log": runtime._log_tail[-60:]}
            results.append(record)
            print("ERROR", json.dumps(record), flush=True)
            raise
        finally:
            if monitor_task:
                monitor_task.cancel()
                await asyncio.gather(monitor_task, return_exceptions=True)
            (OUT / ("results-preservation.json" if preservation else "results-extended.json" if extended else "results.json")).write_text(json.dumps(results, indent=2), encoding="utf8")

    deadline = time.monotonic() + 1200
    while not h3.models_ready:
        if time.monotonic() > deadline:
            raise RuntimeError("Model download did not finish within the benchmark waiting window")
        print("Waiting for model downloads", flush=True)
        await asyncio.sleep(15)
    if preservation:
        data = "data:image/png;base64," + base64.b64encode((OUT / "h3-portrait-pt.png").read_bytes()).decode()
        await run("h3-portrait-preservation-pt", h3, "Mude somente o cabelo da mulher da direita para azul. Preserve os rostos, roupas e o fundo.", [data])
        return
    if extended:
        portrait = await run("h3-portrait-pt", h3, "Foto de duas mulheres adultas sentadas em um banco de jardim. A mulher da esquerda tem cabelo preto curto e camisa branca. A mulher da direita tem cabelo rosa comprido e camisa verde.", [])
        await run("h3-portrait-edit-pt", h3, "Mude somente o cabelo da mulher da direita para azul. Preserve os rostos, roupas e o fundo.", [portrait])
        def data_uri(path):
            return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
        await run("h3-multi-edit-pt", h3, "Mantenha a caneca azul da imagem 1 e coloque a colher azul da imagem 2 na mesa ao lado dela. Preserve o restante.",
                  [data_uri(OUT / "h3-edit-pt.png"), data_uri(OUT / "h3-generate-pt.png")])
        return
    base = await run("h3-generate-pt", h3, "Uma caneca vermelha sobre uma mesa branca, com uma colher azul ao lado. Fotografia.", [])
    edit = "Troque a caneca vermelha por uma azul. Remova a colher. Preserve o resto."
    await run("h3-edit-pt", h3, edit, [base])
    from neveai.routers.image_fast_generation import neve_image_2s_runtime
    await run("image2-edit-pt", neve_image_2s_runtime, edit, [base])
    from neveai.routers.image_quality_generation import neve_image_21_runtime
    await run("image26-edit-pt", neve_image_21_runtime, edit, [base])


if __name__ == "__main__":
    asyncio.run(main())
