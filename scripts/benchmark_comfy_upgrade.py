"""Exercise production image/video runtimes without persisting chats or library items."""
import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
REPORT = ROOT / "logs/runtime-upgrade-20261029"


async def main(args):
    from PIL import Image
    from neveai.routers import image_fast_generation as fast
    original_worker_error = fast.worker_error
    def capture_worker_error(name, status):
        (REPORT / (args.label + "-worker-error.json")).write_text(json.dumps(status, indent=2), encoding="utf-8")
        return original_worker_error(name, status)
    fast.worker_error = capture_worker_error
    if args.force_vbar_once:
        from neveai.utils.image_memory import ImageGenerationError
        original_run_once = fast.NeveImage2SRuntime._run_once
        injected = False
        async def run_with_one_fault(self, *values, **options):
            nonlocal injected
            if not injected:
                injected = True
                raise ImageGenerationError("Neve Image 2 falhou: RuntimeError: Fault failed: 2")
            return await original_run_once(self, *values, **options)
        fast.NeveImage2SRuntime._run_once = run_with_one_fault
    if args.label == "baseline":
        from neveai.routers import image_fast_generation as fast, video_generation as video
        fast.RUNTIME_REVISION = "neve-image-2-turbo-8step-v1-comfy-0.38"
        video.VIDEO_RUNTIME_REVISION = "neve-minimax-h3-fl2va-w4a8-v2-comfy-0.38"
    details = {}
    async def progress(*value):
        print("PROGRESS", *value, flush=True)
    refs = []
    if args.references:
        for index in range(args.references):
            name = ("main", "reference")[index % 2]
            refs.append((ROOT / "logs/image2-modes" / (name + ".png")).read_bytes())
    start = time.perf_counter()
    prompt = "A realistic product photograph of a red ceramic mug beside a closed black notebook on a dark green desk. Clear natural daylight, no text."
    if refs:
        prompt = "Change only the blue jacket to a green jacket. Preserve the man's face, pose, body, trousers and gray studio background."
    if args.engine == "video":
        from neveai.routers.video_generation import minimax_h3_runtime
        runtime = minimax_h3_runtime
        try:
            reference = ("main.png", refs[0], "image/png") if refs else None
            last = ("reference.png", refs[1], "image/png") if len(refs) > 1 else None
            result = await runtime._generate_once(prompt="A red ceramic mug on a green desk. Slow smooth camera orbit, stable objects, soft daylight.",
                progress=progress, image=reference, last_image=last, width=864, height=480, frames=124, seed=42)
            path = REPORT / (args.label + "-video.mp4")
            path.write_bytes(result["video"])
            details = {key: str(value) for key, value in result.items() if key != "video"}
        finally:
            await runtime.stop()
    else:
        if args.engine == "mode":
            from neveai.routers.image_fast_modes import ImageModeOptions, NeveImage2ModeRuntime
            options = dict(mode=args.mode)
            if args.mode == "inpaint":
                import io
                from PIL import ImageDraw
                with Image.open(io.BytesIO(refs[0])) as source:
                    mask = Image.new("L", source.size)
                    ImageDraw.Draw(mask).rectangle((source.width*0.3, source.height*0.3, source.width*0.7, source.height*0.55), fill=255)
                    encoded = io.BytesIO()
                    mask.save(encoded, format="PNG")
                    options["mask"] = "data:image/png;base64," + base64.b64encode(encoded.getvalue()).decode()
            runtime = NeveImage2ModeRuntime(ImageModeOptions(**options))
        elif args.engine == "fast":
            from neveai.routers.image_fast_generation import neve_image_2s_runtime as runtime
        else:
            from neveai.routers.image_quality_generation import neve_image_21_runtime as runtime
        if args.comfy_flag:
            original_command = runtime._comfy_command
            runtime._comfy_command = lambda: [*original_command(), args.comfy_flag]
        with patch("neveai.routers.stable_diffusion._read_image_reference_bytes", side_effect=lambda ref, user: refs[int(ref)]), \
             patch("neveai.routers.image_quality_generation._read_image_reference_bytes", side_effect=lambda ref, user: refs[int(ref)]):
            if args.engine in {"fast", "mode"}:
                data = await runtime._run_once(prompt, "1:1", [str(i) for i in range(len(refs))], None, progress, seed=42)
            else:
                data = await runtime.run(prompt, "1:1", [str(i) for i in range(len(refs))], None, progress, details=details)
        path = REPORT / (args.label + "-" + args.engine + ".png")
        path.write_bytes(base64.b64decode(data.split(",", 1)[1]))
        with Image.open(path) as image:
            details["dimensions"] = image.size
            details["extrema"] = image.getextrema()
    result = dict(engine=args.engine, label=args.label, references=args.references, seconds=time.perf_counter()-start,
                  path=str(path) if path else None, details=details)
    (REPORT / (args.label + "-" + args.engine + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["fast", "quality", "video", "mode"], required=True)
    parser.add_argument("--mode", choices=["inpaint", "outpaint", "restore", "outfit", "body"])
    parser.add_argument("--comfy-flag")
    parser.add_argument("--force-vbar-once", action="store_true")
    parser.add_argument("--references", type=int, default=0)
    parser.add_argument("--label", required=True)
    asyncio.run(main(parser.parse_args()))
