"""Cancel a real isolated H3 worker and confirm all its processes exit."""
import asyncio
import json
from pathlib import Path
import sys
import time
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from neveai.routers.image_h3_generation import neve_image_3_runtime as runtime


async def main():
    start = time.monotonic()
    async def progress(value):
        pass
    task = asyncio.create_task(runtime.run("Uma esfera vermelha sobre uma mesa", "1:1", [], None, progress))
    try:
        while not runtime._prompt_id:
            if task.done():
                await task
                raise AssertionError("Generation finished before the cancellation test")
            if time.monotonic() - start > 300:
                raise TimeoutError("Worker did not accept the prompt")
            await asyncio.sleep(0.1)
        process = psutil.Process(runtime._process.pid)
        pids = [process.pid, *(child.pid for child in process.children(recursive=True))]
        await asyncio.sleep(2)
        task.cancel()
        try:
            await asyncio.wait_for(task, 20)
            raise AssertionError("Task did not report cancellation")
        except asyncio.CancelledError:
            pass
        assert runtime._process is None and runtime._port is None
        assert not runtime._request_lock.locked()
        await asyncio.sleep(1)
        assert not [pid for pid in pids if psutil.pid_exists(pid)], pids
        print(json.dumps({"cancelled": True, "worker_pids_exited": pids, "lock_released": True, "seconds": round(time.monotonic()-start, 2)}))
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runtime.cancel()


if __name__ == "__main__":
    asyncio.run(main())
