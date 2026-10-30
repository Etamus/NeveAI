"""Apply the same pinned installers used by production, with no model inference."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from neveai.routers.image_fast_generation import neve_image_2s_runtime
    from neveai.routers.video_generation import minimax_h3_runtime

    async def progress(*args):
        print(*args, flush=True)
    await neve_image_2s_runtime._install(progress)
    print("IMAGE CORE READY", flush=True)
    await minimax_h3_runtime.ensure_installed(progress)
    print("VIDEO CORE READY", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
