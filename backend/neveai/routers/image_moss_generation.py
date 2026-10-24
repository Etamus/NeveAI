"""Temporary MOSS-Image-SFT experiment, isolated from the Qwen runtimes."""
import asyncio
import base64
import io
import json
import math
import os
import random
import socket
import time
from pathlib import Path

import aiohttp
import httpx
from PIL import Image, ImageOps

from neveai.config import CACHE_DIR
from neveai.utils.image_memory import worker_error

ROOT = CACHE_DIR / "image_moss_generation"
CORE = ROOT / "ComfyUI"
INPUT = ROOT / "input"
OUTPUT = ROOT / "output"
MODEL_INT8 = "moss_image_sft_int8_convrot.safetensors"
MODEL_BF16 = "moss_image_sft_bf16.safetensors"
ENCODER = "qwen3.5_9b_int8_convrot.safetensors"
VAE = "flux2-vae_small.safetensors"
EDIT_LORA = "moss_image_edit.safetensors"
TURBO_LORA = "moss_image_dmd8.safetensors"
MAX_REFERENCES = 4
DEFAULT_PROFILE = {"steps": 8, "cfg": 1.0, "turbo": 1.0, "edit_strength": 1.0, "bf16": False, "reference_edge": 1024}
EDIT_PROFILE = {**DEFAULT_PROFILE, "steps": 12, "cfg": 3.0, "turbo": 0.0}


def _prepare_reference(raw, max_edge):
    with Image.open(io.BytesIO(raw)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    original_size = image.size
    scale = min(1.0, max_edge / max(image.size))
    image = image.resize(tuple(max(16, round(side * scale / 16) * 16) for side in image.size), Image.Resampling.LANCZOS)
    encoded = io.BytesIO()
    image.save(encoded, format="PNG", compress_level=3)
    return encoded.getvalue(), original_size


def moss_image_dimensions(resolution: str, source_size=None) -> tuple[int, int]:
    ratios = {"1:1": (1, 1), "16:9": (16, 9), "9:16": (9, 16), "4:3": (4, 3), "3:4": (3, 4)}
    width, height = source_size or ratios.get(resolution, (1, 1))
    scale = math.sqrt(1152 * 1152 / (width * height))
    return tuple(max(32, round(side * scale / 32) * 32) for side in (width, height))


def build_workflow(prompt, width, height, references, seed, profile=None):
    p = {**DEFAULT_PROFILE, **(profile or {})}
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MODEL_BF16 if p["bf16"] else MODEL_INT8, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": ENCODER, "type": "moss_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "6": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": "neve_image_3"}},
    }
    model = ["1", 0]
    if p["turbo"]:
        graph["7"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": TURBO_LORA, "strength_model": p["turbo"]}}
        model = ["7", 0]
    if references:
        graph["8"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": EDIT_LORA, "strength_model": p["edit_strength"]}}
        model = ["8", 0]
        images = {}
        for index, filename in enumerate(references):
            node = str(20 + index)
            graph[node] = {"class_type": "LoadImage", "inputs": {"image": filename}}
            # Native v3 Autogrow sockets are flattened in API graphs.
            images[f"images.image_{index}"] = [node, 0]
        for key, text in (("4", prompt), ("5", "")):
            graph[key] = {"class_type": "TextEncodeMOSSImageEdit", "inputs": {
                "clip": ["2", 0], "prompt": text, "vae": ["3", 0],
                "edit_format": "Moss-Image-Edit", "image_strength": 1.0, **images,
            }}
    else:
        for key, text in (("4", prompt), ("5", "")):
            graph[key] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": text}}
    if p["cfg"] > 1:
        graph["9"] = {"class_type": "SkipLayerGuidanceDiTSimple", "inputs": {
            "model": model, "double_layers": "22", "single_layers": "", "start_percent": 0.0, "end_percent": 1.0,
        }}
        model = ["9", 0]
    graph["11"] = {"class_type": "KSampler", "inputs": {
        "model": model, "seed": seed, "steps": p["steps"], "cfg": p["cfg"],
        "sampler_name": "euler", "scheduler": "normal" if references else "sgm_uniform",
        "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0], "denoise": 1.0,
    }}
    return graph


class NeveImage3Runtime:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._process = None
        self._log = None
        self._base = None

    async def _start(self):
        if self._process is not None and self._process.returncode is None:
            return self._base
        python = CACHE_DIR / "image_fast_generation/runtime/Scripts/python.exe"
        if not python.is_file() or not (CORE / "main.py").is_file():
            raise RuntimeError("O experimento Neve Image 3 ainda nao foi preparado.")
        for directory in (INPUT, OUTPUT, ROOT / "temp"):
            directory.mkdir(parents=True, exist_ok=True)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self._base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "runtime_packages")
        env["PYTHONIOENCODING"] = "utf-8"
        self._log = (ROOT / "comfy-runtime.log").open("ab")
        self._process = await asyncio.create_subprocess_exec(
            str(python), str(CORE / "main.py"), "--listen", "127.0.0.1", "--port", str(port),
            "--base-directory", str(ROOT), "--input-directory", str(INPUT), "--output-directory", str(OUTPUT),
            "--temp-directory", str(ROOT / "temp"), "--disable-auto-launch", "--disable-all-custom-nodes",
            "--offline", "--preview-method", "none", "--reserve-vram", "0.75", "--cache-lru", "8",
            cwd=str(CORE), env=env, stdout=self._log, stderr=asyncio.subprocess.STDOUT,
            **({"creationflags": 0x08000000} if os.name == "nt" else {}),
        )
        async with httpx.AsyncClient(timeout=2) as client:
            for _ in range(240):
                if self._process.returncode is not None:
                    raise RuntimeError("ComfyUI do Neve Image 3 encerrou. Consulte image_moss_generation/comfy-runtime.log.")
                try:
                    if (await client.get(self._base + "/system_stats")).is_success:
                        return self._base
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.5)
        raise RuntimeError("ComfyUI do Neve Image 3 nao respondeu.")

    async def cancel(self):
        if self._base:
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    await client.post(self._base + "/interrupt")
            except httpx.HTTPError:
                pass
        await self._stop()

    async def _stop(self):
        process, self._process = self._process, None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        if self._log:
            self._log.close()
            self._log = None
        self._base = None

    async def execute(self, base, prompt, resolution, raw_references, progress, dimensions=None, *, seed=None, profile=None, details=None):
        """Submit a measured graph; also used by the isolated benchmark harness."""
        started = time.monotonic()
        uploaded = []
        effective_profile = {**DEFAULT_PROFILE, **(profile or {})}
        width, height = moss_image_dimensions(resolution)
        async with httpx.AsyncClient(base_url=base, timeout=120) as client:
            try:
                for index, raw in enumerate(raw_references):
                    encoded, original_size = await asyncio.to_thread(_prepare_reference, raw, effective_profile["reference_edge"])
                    if index == 0:
                        width, height = moss_image_dimensions(resolution, original_size)
                    response = await client.post("/upload/image", files={"image": (f"moss_ref_{random.getrandbits(64):016x}.png", encoded, "image/png")})
                    response.raise_for_status()
                    uploaded.append(response.json()["name"])
                if (profile or {}).get("output_pixels"):
                    scale = math.sqrt(profile["output_pixels"] / (width * height))
                    width, height = (max(16, round(side * scale / 16) * 16) for side in (width, height))
                if dimensions:
                    await dimensions(width, height)
                graph = build_workflow(prompt, width, height, uploaded, seed if seed is not None else random.getrandbits(63), profile)
                client_id = f"neve-moss-{random.getrandbits(64):016x}"
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(base.replace("http://", "ws://") + "/ws?clientId=" + client_id, heartbeat=30) as ws:
                        response = await client.post("/prompt", json={"prompt": graph, "client_id": client_id})
                        if not response.is_success:
                            raise RuntimeError(f"Workflow MOSS invalido: {response.text[:2500]}")
                        prompt_id = response.json()["prompt_id"]
                        await progress(15)
                        last_poll = 0.0
                        for _ in range(7200):
                            try:
                                event = await asyncio.wait_for(ws.receive(), .5)
                                if event.type == aiohttp.WSMsgType.TEXT:
                                    payload = event.json()
                                    item = payload.get("data", {})
                                    if item.get("prompt_id") == prompt_id:
                                        if payload["type"] == "progress" and item.get("max"):
                                            await progress(min(95, 30 + int(65 * item["value"] / item["max"])))
                                        if payload["type"] == "execution_error":
                                            raise RuntimeError(f"MOSS: {item.get('exception_message', item)}")
                            except asyncio.TimeoutError:
                                pass
                            if time.monotonic() - last_poll < 1:
                                continue
                            last_poll = time.monotonic()
                            result = await client.get("/history/" + prompt_id)
                            result.raise_for_status()
                            history = result.json().get(prompt_id)
                            if not history:
                                continue
                            if history.get("status", {}).get("status_str") == "error":
                                raise worker_error("Neve Image 3", history["status"])
                            images = history.get("outputs", {}).get("13", {}).get("images", [])
                            if not images:
                                continue
                            item = images[0]
                            result = await client.get("/view", params=item)
                            result.raise_for_status()
                            if details is not None:
                                details.update({"model": "OpenMOSS-Team/MOSS-Image-SFT", "profile": {**DEFAULT_PROFILE, **(profile or {})}, "seconds": round(time.monotonic()-started, 3), "references": len(raw_references), "width": width, "height": height, "experimental": True})
                            path = (OUTPUT / item.get("subfolder", "") / item["filename"]).resolve()
                            if path.is_relative_to(OUTPUT.resolve()):
                                path.unlink(missing_ok=True)
                            await progress(99)
                            return "data:image/png;base64," + base64.b64encode(result.content).decode("ascii")
                        raise RuntimeError("Neve Image 3 excedeu o tempo limite.")
            except BaseException:
                try:
                    await client.post("/interrupt")
                except httpx.HTTPError:
                    pass
                raise
            finally:
                for name in uploaded:
                    path = (INPUT / name).resolve()
                    if path.is_relative_to(INPUT.resolve()):
                        path.unlink(missing_ok=True)

    async def run(self, prompt, resolution, references, user_id, progress, dimensions=None, details=None):
        if len(references) > MAX_REFERENCES:
            raise ValueError("Neve Image 3 aceita ate quatro imagens de referencia.")
        if not prompt.strip():
            raise ValueError("Descreva a imagem que deseja criar ou editar.")
        from neveai.routers.stable_diffusion import _read_image_reference_bytes
        async with self._lock:
            try:
                await progress(2)
                base = await self._start()
                raw = [await asyncio.to_thread(_read_image_reference_bytes, reference, user_id) for reference in references]
                return await self.execute(base, prompt, resolution, raw, progress, dimensions,
                                          profile=EDIT_PROFILE if raw else DEFAULT_PROFILE, details=details)
            finally:
                await self._stop()


neve_image_3_runtime = NeveImage3Runtime()
