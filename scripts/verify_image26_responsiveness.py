"""Compare identical preprocessing inline/worker, without inference or persistence."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.routers import image_quality_generation as quality


async def sample(operation):
    gaps = []
    async def heartbeat():
        previous = time.perf_counter()
        while True:
            await asyncio.sleep(.005)
            now = time.perf_counter()
            gaps.append((now - previous - .005) * 1000)
            previous = now
    task = asyncio.create_task(heartbeat())
    await asyncio.sleep(.03)
    begin = time.perf_counter()
    value = await operation()
    elapsed = time.perf_counter() - begin
    await asyncio.sleep(.03)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return value, {"seconds": elapsed, "max_event_loop_delay_ms": max(gaps)}


async def main():
    raw = (ROOT / "backend/data/uploads/0e335168-40a8-473e-a233-1dd5f1cfb0c6_image.png").read_bytes()
    runtime = quality.NeveImage21Runtime()
    dimensions = quality._reference_dimensions(raw)
    size = runtime._reference_size(*dimensions, quality.EDIT_MODEL_FILE, 0, 1, optimized_edit=True)
    planning_size = runtime._reference_size(*dimensions, quality.EDIT_MODEL_FILE, 0, 1, detail_canvas=False)
    def work():
        return quality._encode_reference(raw, size, planning_size), runtime._pe_file()
    async def inline():
        return work()
    async def worker():
        return await asyncio.to_thread(work)
    results = []
    for _ in range(3):
        before, baseline = await sample(inline)
        after, fixed = await sample(worker)
        assert before == after, "Reference/planner bytes or PE model changed"
        results.append({"inline": baseline, "worker": fixed})
    evidence = {"size": size, "planning_size": planning_size, "sha256": [hashlib.sha256(b).hexdigest() for b in after[0]], "samples": results}
    output = ROOT / "logs/image-latency-20261114/preprocessing-fix.json"
    output.write_text(json.dumps(evidence, indent=2), encoding="utf8")
    print(json.dumps(evidence, indent=2))


asyncio.run(main())
