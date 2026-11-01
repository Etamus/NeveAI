"""Deterministic local latency/concurrency comparison, without network or inference."""
import asyncio
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace as NS
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
spec = importlib.util.spec_from_file_location("web_benchmark", root / "backend/neveai/retrieval/web/research.py")
web = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"neveai.utils.url": NS(validate_url=lambda url: True)}):
    spec.loader.exec_module(web)


async def original(reader, urls, limit):
    async def batch(values):
        tasks = [asyncio.create_task(reader(url)) for url in values]
        done, _ = await asyncio.wait(tasks, timeout=.4)
        result = [task.result() for task in tasks if task in done and not task.exception() and task.result()]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return result
    pages = await batch(urls[:limit])
    if len(pages) < limit:
        pages.extend(await batch(urls[limit:limit + limit - len(pages)]))
    return pages


async def measure(kind, mode):
    calls, active, peak = 0, 0, 0
    async def read(index):
        nonlocal calls, active, peak
        calls += 1; active += 1; peak = max(peak, active)
        try:
            delay = 1 if mode == "stalled" and index < 4 else .24 if mode == "failure" and index < 4 else .1
            if mode == "failure" and index == 0:
                delay = .001
            await asyncio.sleep(delay)
            if mode == "failure" and index == 0:
                return None
            return {"content": "Actual extracted evidence. " * 5, "metadata": {"source": str(index)}}
        finally:
            active -= 1
    start = time.perf_counter()
    result = await (original(read, list(range(8)), 4) if kind == "before" else web.read_candidates(read, list(range(8)), 4, timeout=.4, hedge_after=.03 if mode == "stalled" else .2))
    elapsed = (time.perf_counter() - start) * 1000
    assert len(result) == 4 and active == 0 and peak <= 6 and calls <= 8
    return elapsed


async def main():
    rows = []
    for mode in ("healthy", "failure", "stalled"):
        old, new = [], []
        for _ in range(7):
            old.append(await measure("before", mode))
            new.append(await measure("after", mode))
        rows.append({"scenario": mode, "before_median_ms": round(statistics.median(old), 2),
                     "after_median_ms": round(statistics.median(new), 2)})
    print(json.dumps(rows, indent=2))


asyncio.run(main())
