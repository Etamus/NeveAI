"""Controlled video comparisons. Overrides live only in this process, never in app settings."""
import argparse
import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path
import sys
import time

import av
import numpy as np
from PIL import Image, ImageDraw

from test_video_audio_live import inspect_video, monitor, require_idle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
OUTPUT = ROOT / "logs/video-sweetspot-20261102"
PROMPTS = {
    "vlog": 'Fa\u00e7a uma garota japonesa de cabelo rosa conversando como se estivesse falando para um vlog realista, '
    'ela deve falar portugues a frase "Isso \u00e9 um teste de \u00e1udio"',
    "anime": 'Fa\u00e7a uma cena de duas garotas lutando com espadas em um estilo visual de anime dos anos 90',
    "portrait": "Photorealistic medium shot of an adult woman with freckles, natural skin texture and curly brown hair, "
    "wearing a dark green knitted sweater in a sunlit garden. She slowly turns her head toward the camera and smiles. "
    "Realistic facial anatomy, soft daylight, consistent foliage, steady camera. Audio: quiet birds and gentle wind. No music or speech.",
    "motion": "Photorealistic full-body shot of an adult man wearing a red cotton jacket and blue jeans walking from left to right "
    "across a cobblestone courtyard beside a stone wall. Natural proportions, realistic fabric and stone textures, stable tracking camera. "
    "Audio: footsteps on stone, soft outdoor ambience. No music or speech.",
}


def fingerprint(path):
    digest = hashlib.sha256()
    with av.open(str(path)) as container:
        for frame in container.decode(video=0):
            digest.update(frame.to_ndarray(format="rgb24").tobytes())
    return digest.hexdigest()


def contact_sheet(path):
    with av.open(str(path)) as container:
        frames = [frame.to_image() for i, frame in enumerate(container.decode(video=0)) if i in (0, 24, 60, 100)]
    sheet = Image.new("RGB", (640 * len(frames), 400), "#222222")
    for i, frame in enumerate(frames):
        frame.thumbnail((640, 360))
        sheet.paste(frame, (640 * i, 30))
    ImageDraw.Draw(sheet).text((8, 8), path.stem, fill="white")
    sheet.save(path.with_suffix(".sheet.jpg"), quality=95)


async def main(args):
    if args.download:
        os.environ["HF_HUB_DISABLE_XET"] = "1"
    from neveai.routers.video_generation import minimax_h3_runtime
    from neveai.routers.video_vdn_generation import vdn_h3_runtime
    from neveai.routers.video_quality_generation import video15_runtime
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.collect_user:
        import httpx
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8080", timeout=60) as client:
            response = await client.get("/api/v1/files/generated", params={"kind": "video", "limit": 8})
            response.raise_for_status()
            for item in response.json():
                data = item.get("meta", {}).get("data", {})
                if data.get("video_model") not in {"minimax_h3", "vdn_h3"}:
                    continue
                path = OUTPUT / f"user-{item['id']}.mp4"
                response = await client.get(f"/api/v1/files/{item['id']}/content")
                response.raise_for_status()
                path.write_bytes(response.content)
                path.with_suffix(".json").write_text(json.dumps(data, indent=2), encoding="utf8")
                await asyncio.to_thread(contact_sheet, path)
        return
    if args.download:
        from huggingface_hub import HfApi
        import requests
        items = {
            "w6": ("Comfy-Org/MiniMax-H3", "diffusion_models/minimax_h3_fl2va_pruned_w6a8.safetensors"),
            "vae": ("Comfy-Org/MiniMax-H3", "vae/minimax_h3_video_vae_fp16.safetensors"),
            "singularity": ("WarmBloodAban/Minimax-h3_Singularity", "Minimax-h3_Singularity_ref2va_v2_pruned_int8.safetensors"),
            "encoder32": ("Comfy-Org/MiniMax-H3", "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"),
        }
        from neveai.routers.video_generation import COMFYUI_MODELS
        for name in args.download:
            repo, filename = items[name]
            info = HfApi().model_info(repo, files_metadata=True)
            revision = info.sha
            destination = COMFYUI_MODELS / "diffusion_models" if name == "singularity" else COMFYUI_MODELS
            path = destination / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            metadata = next(file for file in info.siblings if file.rfilename == filename)
            expected = metadata.lfs.sha256
            if not path.is_file():
                partial = path.with_suffix(".study-download")
                print("HTTP DOWNLOAD", name, metadata.size, flush=True)
                digest, downloaded = hashlib.sha256(), 0
                with requests.get(f"https://huggingface.co/{repo}/resolve/{revision}/{filename}",
                                  stream=True, timeout=(30, 120)) as response:
                    response.raise_for_status()
                    with partial.open("wb") as output:
                        for chunk in response.iter_content(4 * 1024 * 1024):
                            output.write(chunk); digest.update(chunk)
                            previous = downloaded // (512 * 1024 * 1024)
                            downloaded += len(chunk)
                            if downloaded // (512 * 1024 * 1024) != previous:
                                print(name, downloaded, "/", metadata.size, flush=True)
                assert downloaded == metadata.size and digest.hexdigest() == expected
                partial.replace(path)
            (OUTPUT / (name + "-weights.json")).write_text(json.dumps(dict(repo=repo, file=filename,
                revision=revision, path=str(path), sha256=expected, bytes=path.stat().st_size), indent=2), encoding="utf8")
            print("DOWNLOADED", name, path, flush=True)
        return
    for case in args.case:
        variant, resolution, scene = case.split(":")
        width, height = (864, 480) if resolution == "480" else (1184, 672)
        runtime = video15_runtime if variant.startswith("quality") else (
            vdn_h3_runtime if variant.startswith("vdn") else minimax_h3_runtime)
        builder = type(runtime)._build_workflow

        def build(*params, **kwargs):
            if variant.startswith("decode"):
                return {
                    "1": {"class_type": "LoadLatent", "inputs": {"latent": "neve-study-" + scene + ".latent"}},
                    "3": {"class_type": "VAELoader", "inputs": {"vae_name":
                        "minimax_h3_video_vae_fp16.safetensors" if "fp16" in variant else "minimax_h3_video_vae_int8_convrot.safetensors"}},
                    "14": {"class_type": "VAEDecode", "inputs": {"samples": ["1", 0], "vae": ["3", 0]}},
                    "15": {"class_type": "CreateVideo", "inputs": {"images": ["14", 0], "fps": 24.0}},
                    "16": {"class_type": "SaveVideo", "inputs": {"video": ["15", 0], "filename_prefix": "study/decode",
                        "format": "mp4", "format.codec": "h264", "format.codec.encoding": "re-encode", "format.codec.encoding.crf": 18.0}},
                }
            graph = builder(*params, **kwargs)
            if variant.endswith("silent"):
                graph.pop("17"); graph.pop("18"); graph["15"]["inputs"].pop("audio")
            if "res8" in variant:
                graph["11"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}}
            if "soft" in variant:
                graph["7"]["inputs"]["strength"] = 0.9
            if "six" in variant:
                graph["9"]["inputs"]["steps"] = 6
            if "native" in variant:
                graph.pop("7")
                graph["8"]["inputs"]["model"] = ["6", 0]
                graph["9"]["inputs"].update(model=["6", 0], steps=20, scheduler="simple")
                if "native12" in variant:
                    graph["9"]["inputs"]["steps"] = 12
                graph["11"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}}
            if "w6" in variant:
                graph["6"]["inputs"]["unet_name"] = "minimax_h3_fl2va_pruned_w6a8.safetensors"
            if "singularity" in variant:
                graph["6"]["inputs"]["unet_name"] = "Minimax-h3_Singularity_ref2va_v2_pruned_int8.safetensors"
            if "fp16vae" in variant:
                graph["3"]["inputs"]["vae_name"] = "minimax_h3_video_vae_fp16.safetensors"
            if args.capture:
                graph["90"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["13", 0]}}
                graph["91"] = {"class_type": "SaveLatent", "inputs": {"samples": ["90", 0],
                    "filename_prefix": "study/" + case.replace(":", "-")}}
            return graph

        runtime._build_workflow = build
        await require_idle()
        name = case.replace(":", "-")
        if args.references or args.frames != 124:
            name += f"-{args.references}refs-{args.frames}f"
        path = OUTPUT / (name + ".mp4")
        if path.exists() and not args.repeat:
            print("SKIP", name, flush=True)
            continue
        events, gpu = [], []
        start = time.perf_counter()

        async def progress(description, value=None):
            events.append({"seconds": time.perf_counter()-start, "description": description, "progress": value})
            print(name, round(events[-1]["seconds"], 1), description, value, flush=True)

        sampler = asyncio.create_task(monitor(gpu))
        input_latent = None
        try:
            await runtime.prepare(progress)
            if variant.startswith("decode"):
                input_latent = runtime._worker_paths()[1] / ("neve-study-" + scene + ".latent")
                input_latent.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(OUTPUT / (scene + ".latent"), input_latent)
            images = [(f"study-{part}.png", (OUTPUT / f"h3-w6-480-vlog.{part}.png").read_bytes(), "image/png")
                      for part in ("first", "last")[:args.references]]
            result = await runtime._generate_once(PROMPTS.get(scene, "Decode captured test latent"), progress, width=width, height=height,
                frames=args.frames, seed=args.seed, low_vram_lora=args.merged,
                image=images[0] if images else None, last_image=images[1] if len(images) > 1 else None)
            seconds = time.perf_counter()-start
            path.write_bytes(result["video"])
            if args.capture:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"http://127.0.0.1:{runtime._port}/history/{runtime._prompt_id}")
                    response.raise_for_status()
                    saved = response.json()[runtime._prompt_id]["outputs"]["91"]["latents"][0]
                    root = runtime._worker_paths()[2].resolve()
                    source = (root / saved["subfolder"] / saved["filename"]).resolve()
                    assert source.is_relative_to(root)
                    shutil.copy2(source, path.with_suffix(".latent"))
            if variant.endswith("silent") or variant.startswith("decode"):
                with av.open(str(path)) as media:
                    assert not media.streams.audio
                inspection = {"silent": True}
            else:
                inspection = await asyncio.to_thread(inspect_video, path)
            await asyncio.to_thread(contact_sheet, path)
            sha = await asyncio.to_thread(fingerprint, path)
            row = dict(case=case, seconds=seconds, seed=args.seed, merged=args.merged, inspection=inspection,
                       video_sha256=sha, gpu=gpu, progress=events, worker_log=list(runtime._log_tail))
            path.with_suffix(".json").write_text(json.dumps(row, indent=2), encoding="utf8")
            print("PASS", name, seconds, sha, flush=True)
        except Exception as error:
            path.with_suffix(".error.json").write_text(json.dumps(dict(case=case, error=str(error),
                worker_log=list(runtime._log_tail), gpu=gpu), indent=2), encoding="utf8")
            print("FAIL", name, str(error), flush=True)
            if not args.keep_going:
                raise
        finally:
            sampler.cancel()
            try:
                await sampler
            except asyncio.CancelledError:
                pass
            await runtime.stop()
            del runtime._build_workflow
            if input_latent:
                assert input_latent.resolve().is_relative_to(runtime._worker_paths()[1].resolve())
                input_latent.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--download", action="append", choices=["w6", "vae", "singularity", "encoder32"])
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--merged", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--collect-user", action="store_true")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--references", type=int, choices=[0, 1, 2], default=0)
    parser.add_argument("--frames", type=int, default=124)
    asyncio.run(main(parser.parse_args()))
