"""Real H3/VDN native audio validation; writes evidence only, never saves chats."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import time

import av
import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
OUTPUT = ROOT / "logs/video-audio-20261102"
PROMPT = (
    "Close-up of water being slowly poured from a small metal teapot into a white ceramic cup "
    "on a wooden table. A visible stream of water and gentle ripples inside the cup. "
    "Steady camera, natural daylight, realistic movement. "
    "Audio: clear gentle pouring water, light splashes, quiet room ambience. "
    "No speech, no music, no text."
)


def inspect_video(path):
    with av.open(str(path)) as container:
        assert len(container.streams.video) == 1
        assert len(container.streams.audio) == 1, "Missing native audio stream"
        video, audio = container.streams.video[0], container.streams.audio[0]
        metadata = dict(width=video.width, height=video.height, fps=float(video.average_rate),
                        video_codec=video.codec_context.name, audio_codec=audio.codec_context.name,
                        sample_rate=audio.codec_context.sample_rate,
                        channels=audio.codec_context.channels)
        frames, previous, motion = [], None, []
        count = 0
        for frame in container.decode(video=0):
            if count % 24 == 0:
                pixels = frame.to_ndarray(format="rgb24")
                assert pixels.std() > 5, "Blank video"
                if previous is not None:
                    motion.append(float(np.abs(pixels.astype(float) - previous).mean()))
                previous = pixels.astype(float)
                frames.append(frame.to_image())
            count += 1
        metadata.update(frames=count, video_seconds=count / metadata["fps"], motion=max(motion))
        assert metadata["motion"] > 0.1, "Static video"
        frames[0].save(path.with_suffix(".first.png"))
        frames[-1].save(path.with_suffix(".last.png"))
    with av.open(str(path)) as container:
        wave = np.concatenate([frame.to_ndarray() for frame in container.decode(audio=0)], axis=-1)
    assert np.isfinite(wave).all(), "Non-finite audio samples"
    metadata.update(audio_seconds=wave.shape[-1] / metadata["sample_rate"],
                    audio_rms=float(np.sqrt(np.mean(wave.astype(float) ** 2))),
                    audio_peak=float(np.abs(wave).max()),
                    clipped_fraction=float((np.abs(wave) >= 0.999).mean()))
    assert metadata["channels"] == 2
    assert metadata["sample_rate"] == 32000
    assert metadata["audio_codec"] == "aac"
    assert metadata["audio_rms"] > 0.0001, "Silent audio"
    assert abs(metadata["audio_seconds"] - metadata["video_seconds"]) < 0.1, metadata
    return metadata


async def require_idle():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8080", timeout=10) as client:
        response = await client.get("/api/tasks")
        response.raise_for_status()
        assert not response.json()["tasks"], "The app has an active task"
        response = await client.get("/llamacpp/models/loaded")
        response.raise_for_status()
        assert not response.json()["models"], "Release the chat model before isolated GPU tests"


async def monitor(samples):
    while True:
        process = await asyncio.create_subprocess_exec(
            "nvidia-smi", "--query-gpu=memory.used,temperature.gpu,power.draw", "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        try:
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                values = [float(value.strip()) for value in stdout.decode().strip().splitlines()[0].split(",")]
                samples.append(dict(seconds=time.monotonic(), vram_mib=values[0], temperature_c=values[1], watts=values[2]))
        finally:
            if process.returncode is None:
                process.terminate()
                await process.wait()
        await asyncio.sleep(2)


async def test_api(prompt=PROMPT, video_models=("minimax_h3", "vdn_h3")):
    results = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8080", timeout=900) as client:
        catalog = await client.get("/api/models")
        catalog.raise_for_status()
        model = catalog.json()["data"][0]["id"]
        for video_model in video_models:
            await require_idle()
            before = await client.get("/api/v1/files/generated", params={"kind": "video", "limit": 100})
            before.raise_for_status()
            previous = {item["id"] for item in before.json()}
            created = []
            started = time.perf_counter()
            try:
                response = await client.post("/api/chat/completions", json={
                    "model": model, "stream": False,
                    "messages": [{"role": "user", "content": prompt}],
                    "features": {"video_generation": True, "video_generation_model": video_model,
                                 "video_generation_resolution": "480p", "video_generation_duration": "5s"},
                })
                response.raise_for_status()
                elapsed = time.perf_counter() - started
                after = await client.get("/api/v1/files/generated", params={"kind": "video", "limit": 100})
                after.raise_for_status()
                created = [item for item in after.json() if item["id"] not in previous
                           and item.get("meta", {}).get("data", {}).get("prompt") == prompt
                           and item.get("meta", {}).get("data", {}).get("video_model") == video_model]
                assert len(created) == 1, response.text
                metadata = created[0]["meta"]["data"]
                if video_model == "vdn_h3":
                    assert metadata["source"] == "minimax-h3-fl2va-w6a8", metadata
                assert not {'prompt_prepared','prepared_prompt','prompt_preparation_error'} & metadata.keys(), metadata
                media = await client.get(f"/api/v1/files/{created[0]['id']}/content")
                media.raise_for_status()
                path = OUTPUT / f"{video_model}-api.mp4"
                path.write_bytes(media.content)
                metrics = await asyncio.to_thread(inspect_video, path)
                results.append(dict(model=video_model, seconds=elapsed, library_registered=True, inspection=metrics, metadata=metadata))
                print("PASS API", video_model, json.dumps(results[-1]), flush=True)
            finally:
                for item in created:
                    deleted = await client.delete(f"/api/v1/files/{item['id']}")
                    deleted.raise_for_status()
    (OUTPUT / "api-results.json").write_text(json.dumps(results, indent=2), encoding="utf8")


async def main(args):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.api:
        prompt=args.prompt or PROMPT
        if args.prompt_record:
            prompt=json.loads(args.prompt_record.read_text(encoding='utf8'))['original']
        await test_api(prompt,args.model or ("minimax_h3", "vdn_h3"))
        return
    from neveai.routers.video_generation import minimax_h3_runtime
    from neveai.routers.video_quality_generation import video15_runtime as vdn_h3_runtime
    cases = [
        ("h3-text", minimax_h3_runtime, 0, 864, 480, 124),
        ("vdn-text", vdn_h3_runtime, 0, 864, 480, 124),
        ("h3-first-frame", minimax_h3_runtime, 1, 480, 864, 124),
        ("vdn-first-last", vdn_h3_runtime, 2, 864, 480, 196),
    ]
    results = []
    for name, runtime, references, width, height, frames in cases:
        if args.case and name not in args.case:
            continue
        await require_idle()
        events, gpu = [], []
        started = time.perf_counter()

        async def progress(description, value=None):
            events.append(dict(seconds=time.perf_counter() - started, description=description, progress=value))
            print(name, round(events[-1]["seconds"], 2), description, value, flush=True)

        images = []
        for extension in ("first", "last")[:references]:
            source = OUTPUT / f"h3-text.{extension}.png"
            images.append((source.name, source.read_bytes(), "image/png"))
        monitor_task = asyncio.create_task(monitor(gpu))
        try:
            await runtime.prepare(progress)
            result = await runtime._generate_once(
                PROMPT, progress, image=images[0] if images else None,
                last_image=images[1] if len(images) > 1 else None,
                width=width, height=height, frames=frames, seed=42)
            elapsed = time.perf_counter() - started
            path = OUTPUT / (name + ".mp4")
            path.write_bytes(result["video"])
            metrics = await asyncio.to_thread(inspect_video, path)
            assert (metrics["width"], metrics["height"]) == (width, height), metrics
            row = dict(case=name, seconds=elapsed, bytes=path.stat().st_size,
                       inspection=metrics, progress=events, gpu=gpu)
            path.with_suffix(".json").write_text(json.dumps(row, indent=2), encoding="utf8")
            results.append(row)
            print("PASS", name, json.dumps(metrics), "seconds", elapsed, flush=True)
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            await runtime.stop()
    (OUTPUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append")
    parser.add_argument("--api", action="store_true")
    parser.add_argument("--prompt")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prompt-record", type=Path)
    parser.add_argument("--model", action="append", choices=["minimax_h3", "vdn_h3"])
    args = parser.parse_args()
    if args.output:
        OUTPUT = args.output
    asyncio.run(main(args))
