"""Real isolated video generation without persisting chats or library entries."""
import argparse
import asyncio
import io
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def inspect_video(path):
    import av
    import numpy as np
    from PIL import Image
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        samples = []
        count = 0
        first = middle = last = None
        for frame in container.decode(video=0):
            count += 1
            if count in (1, 60):
                samples.append(frame.to_ndarray(format="rgb24"))
            if count == 1:
                first = frame.to_image()
            if count == 60:
                middle = frame.to_image()
            last = frame.to_image()
        samples.append(np.asarray(last))
        assert count > 1 and all(float(sample.std()) > 5 for sample in samples), "Blank output"
        motion = float(np.abs(samples[0].astype(float) - samples[-1].astype(float)).mean())
        assert motion > 0.1, "Static output"
        sheet = Image.new("RGB", (stream.width * 3, stream.height))
        for index, frame in enumerate((first, middle or last, last)):
            sheet.paste(frame, (index * stream.width, 0))
        sheet.thumbnail((1800, 600))
        sheet.save(path.with_suffix(".png"))
        return dict(width=stream.width, height=stream.height, frames=count,
                    fps=float(stream.average_rate), frame_difference=motion)


async def main(args):
    from PIL import Image
    from neveai.routers.video_generation import minimax_h3_runtime
    from neveai.routers.video_vdn_generation import vdn_h3_runtime
    runtime = vdn_h3_runtime if args.model == "vdn" else minimax_h3_runtime
    report = ROOT / "logs/vdn-study-20261031"
    report.mkdir(parents=True, exist_ok=True)

    async def progress(*values):
        print(*values, flush=True)
        if args.cancel_after and len(values) > 1 and isinstance(values[1], int) and values[1] >= args.cancel_after:
            await runtime.cancel()

    references = []
    if args.references:
        with Image.open(ROOT / "logs/runtime-upgrade-20261029/removal-smoke-fast.png") as source:
            for index in range(args.references):
                image = source.convert("RGB")
                if index:
                    image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                output = io.BytesIO()
                image.save(output, format="PNG")
                references.append((f"reference-{index}.png", output.getvalue(), "image/png"))
    started = time.perf_counter()
    try:
        await runtime.prepare(progress)
        result = await runtime._generate_once(
            "A red ceramic mug beside a black notebook on a green desk. Slow smooth camera orbit, "
            "stable objects, natural daylight, realistic reflections. No text.", progress,
            image=references[0] if references else None,
            last_image=references[1] if len(references) > 1 else None,
            width=args.width, height=args.height, frames=args.frames, seed=42)
        path = report / f"{args.model}-{args.references}refs-{args.width}x{args.height}-{args.frames}f.mp4"
        path.write_bytes(result["video"])
        metadata = dict(model=args.model, references=args.references,
                        seconds=time.perf_counter()-started, path=str(path), bytes=len(result["video"]))
        metadata["inspection"] = inspect_video(path)
        path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(json.dumps(metadata), flush=True)
    except asyncio.CancelledError:
        if not args.cancel_after:
            raise
        assert runtime._process is None
        (report / "cancellation.json").write_text(json.dumps({
            "cancelled": True, "seconds": time.perf_counter() - started,
            "worker_stopped": runtime._process is None,
        }), encoding="utf-8")
        print("Cancellation released the worker", flush=True)
    finally:
        await runtime.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["vdn", "original"], default="vdn")
    parser.add_argument("--references", type=int, choices=[0, 1, 2], default=0)
    parser.add_argument("--width", type=int, default=864)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--frames", type=int, default=124)
    parser.add_argument("--cancel-after", type=int, default=0)
    asyncio.run(main(parser.parse_args()))
