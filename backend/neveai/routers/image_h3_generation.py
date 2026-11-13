"""Neve Image 3: isolated MiniMax-H3-Image ComfyUI worker, never a video checkpoint."""
from __future__ import annotations

import asyncio
import base64
import io
import math
import os
import random
import re
import socket
import sys

import aiohttp
import httpx
from PIL import Image, ImageOps

from neveai.config import CACHE_DIR
from neveai.routers.image_fast_generation import NeveImage2SRuntime, _process_kwargs, _sha256
from neveai.utils.comfy_runtime import install_comfy_source
from neveai.utils.image_memory import monotonic_progress, worker_error

QUALITY = "minimax_h3_image"
ROOT = CACHE_DIR / "image_h3_generation"
COMFY = ROOT / "ComfyUI"
PYTHON = ROOT / "runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MODELS = ROOT / "models"
COMFY_COMMIT = "989d93d0d968e704c589ce0146bb18c77f6b50cc"  # v0.45.0; other runtimes remain pinned separately.
MODEL_REPO = "Comfy-Org/MiniMax-H3-Image"
MODEL_REVISION = "0bb149f51e3156ed4b90dd45d5620346bfe1df8f"
MODEL = "minimax_h3_image_pruned_w4a8.safetensors"
ENCODER = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VAE = "minimax_h3_image_vae_fp16.safetensors"
ASSETS = (
    ("diffusion_models/" + MODEL, 12549794530, "517cc19b85348386f4df7c806dce80d839d0899e7cdaa3e1dbb09de964381dbb"),
    ("text_encoders/" + ENCODER, 15687142551, "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6"),
    ("vae/" + VAE, 1168505312, "d80e9c2e5cfc9844869961ff5a58c9a9e52182df6bfb30b26018dd7f348721af"),
)
MAX_REFERENCES = 10  # Match the existing composer contract, within the model's 16-image limit.
REVISION = "h3-image-w4a8-6step-v1"


def canvas_size(resolution: str, image_size=None, megapixels=4):
    ratio = image_size[0] / image_size[1] if image_size else {
        "1:1": 1, "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "3:4": 3 / 4,
    }.get(resolution, 1)
    area = megapixels * 1024 * 1024
    return tuple(max(32, round(v / 32) * 32) for v in (math.sqrt(area * ratio), math.sqrt(area / ratio)))


def reference_prompt(prompt: str, count: int) -> str:
    if not count:
        return prompt
    prompt = re.sub(
        r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(?<!<)\b(?:image|imagem|picture)\s*(\d+)\b(?!>)''',
        lambda match: match[1] or f"<Picture {match[2]}>", prompt, flags=re.I,
    )
    instruction = f"Edit <Picture 1>. {prompt}" if not prompt.lstrip().startswith("Edit <Picture") else prompt
    return instruction + (
        " Change only what the user requests. Preserve every unrequested attribute, including "
        "the original colors, clothing, faces, pose, composition and background of <Picture 1>. "
        "Do not spread an attribute change to unrelated objects or regions."
    )


class NeveImage3Runtime(NeveImage2SRuntime):
    """Reuse only subprocess/cancel transport; assets, installation and graph are independent."""

    @property
    def is_installed(self):
        marker = ROOT / ".ready"
        return PYTHON.is_file() and (COMFY / "main.py").is_file() and marker.is_file() and marker.read_text() == REVISION

    @property
    def models_ready(self):
        return all((MODELS / name).is_file() and (MODELS / name).stat().st_size == size for name, size, _ in ASSETS)

    async def _install(self, progress):
        if self.is_installed:
            return
        ROOT.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(install_comfy_source, COMFY, COMFY_COMMIT)
        if not PYTHON.is_file():
            await self._command([sys.executable, "-m", "uv", "venv", str(PYTHON.parent.parent), "--python", sys.executable])
        await self._command([sys.executable, "-m", "uv", "pip", "install", "--python", str(PYTHON),
                             "torch==2.11.0", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu130"])
        await self._command([sys.executable, "-m", "uv", "pip", "install", "--python", str(PYTHON),
                             "-r", str(COMFY / "requirements.txt"), "torch==2.11.0", "huggingface_hub>=0.34,<2"])
        await self._command([str(PYTHON), "-c", "import torch; assert torch.cuda.is_available(), 'CUDA indisponivel'"])
        (ROOT / ".ready").write_text(REVISION)
        await progress(8)

    async def _models(self, progress):
        from huggingface_hub import hf_hub_download
        for name, size, sha in ASSETS:
            path = MODELS / name
            if not path.is_file() or path.stat().st_size != size:
                await asyncio.to_thread(hf_hub_download, repo_id=MODEL_REPO, revision=MODEL_REVISION,
                                        filename=name, local_dir=str(MODELS))
            signature = (path.stat().st_size, path.stat().st_mtime_ns)
            if signature[0] != size:
                raise RuntimeError(f"Neve Image 3: arquivo incompleto: {path.name}")
            if self._verified_assets.get(path) != signature:
                if await asyncio.to_thread(_sha256, path) != sha:
                    raise RuntimeError(f"Neve Image 3: integridade invalida: {path.name}")
                self._verified_assets[path] = signature
        await progress(18)

    def _comfy_command(self):
        return [str(PYTHON), str(COMFY / "main.py"), "--listen", "127.0.0.1", "--port", str(self._port),
                "--base-directory", str(ROOT), "--input-directory", str(ROOT / "input"),
                "--output-directory", str(ROOT / "output"), "--temp-directory", str(ROOT / "temp"),
                "--disable-auto-launch", "--preview-method", "none", "--cache-none", "--reserve-vram", "1",
                "--disable-metadata"]

    async def _start(self, progress):
        for name in ("input", "output", "temp", "custom_nodes", "user"):
            (ROOT / name).mkdir(parents=True, exist_ok=True)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self._port = listener.getsockname()[1]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
        self._log_tail.clear()
        self._process = await asyncio.create_subprocess_exec(*self._comfy_command(), cwd=str(COMFY), env=env,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **_process_kwargs())
        self._log_task = asyncio.create_task(self._capture_logs(self._process))
        base = f"http://127.0.0.1:{self._port}"
        async with httpx.AsyncClient(timeout=2) as client:
            for _ in range(240):
                if self._process.returncode is not None:
                    raise RuntimeError("Neve Image 3: falha no worker:\n" + "\n".join(self._log_tail[-25:]))
                try:
                    if (await client.get(base + "/system_stats")).is_success:
                        return base
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
        raise RuntimeError("Neve Image 3: tempo de inicializacao excedido")

    @staticmethod
    def build_workflow(prompt, width, height, refs, seed):
        if len(refs) > MAX_REFERENCES:
            raise ValueError("Neve Image 3 aceita ate dez referencias.")
        graph = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MODEL, "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": ENCODER, "type": "minimax", "device": "default"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
            "4": {"class_type": "MiniMaxH3ImageConditioning", "inputs": {"clip": ["2", 0], "vae": ["3", 0],
                   "prompt": reference_prompt(prompt, len(refs)), "width": width, "height": height}},
            "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
            "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
                   "latent_image": ["4", 1], "seed": seed, "steps": 6, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
            "13": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "neve_image_3"}},
        }
        for index, filename in enumerate(refs, 1):
            node = str(20 + index)
            graph[node] = {"class_type": "LoadImage", "inputs": {"image": filename}}
            graph["4"]["inputs"][f"images.image_{index}"] = [node, 0]
        return graph

    async def run(self, prompt, resolution, references, user_id, progress, dimensions=None, *, details=None):
        if not prompt.strip() or len(references) > MAX_REFERENCES:
            raise ValueError("Neve Image 3 requer um pedido e aceita ate dez referencias.")
        async with self._request_lock:
            report = monotonic_progress(progress)
            uploaded, output = [], None
            progress_task = None
            try:
                await report(1)
                await self._install(report)
                await self._models(report)
                base = await self._start(report)
                width, height = canvas_size(resolution)
                async with httpx.AsyncClient(base_url=base, timeout=120) as client:
                    from neveai.routers.stable_diffusion import _read_image_reference_bytes
                    for index, ref in enumerate(references):
                        raw = await asyncio.to_thread(_read_image_reference_bytes, ref, user_id)
                        def encode(raw=raw):
                            with Image.open(io.BytesIO(raw)) as opened:
                                image = ImageOps.exif_transpose(opened).convert("RGB")
                            size = image.size
                            image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                            buffer = io.BytesIO()
                            image.save(buffer, "PNG", compress_level=3)
                            return buffer.getvalue(), size
                        data, size = await asyncio.to_thread(encode)
                        if index == 0:
                            width, height = canvas_size(resolution, size)
                        response = await client.post("/upload/image", files={"image": (f"neve3_{random.getrandbits(64):016x}.png", data, "image/png")}, data={"overwrite": "false", "type": "input"})
                        response.raise_for_status()
                        uploaded.append(response.json()["name"])
                    if dimensions:
                        await dimensions(width, height)
                    await report(28)
                    graph = self.build_workflow(prompt, width, height, uploaded, random.getrandbits(63))
                    response = await client.post("/prompt", json={"prompt": graph})
                    if not response.is_success:
                        raise RuntimeError(f"Workflow Neve Image 3 invalido: {response.text[:2000]}")
                    self._prompt_id = response.json()["prompt_id"]
                    progress_task = asyncio.create_task(self._watch_progress(base, self._prompt_id, report))
                    start = asyncio.get_running_loop().time()
                    while asyncio.get_running_loop().time() - start < 1800:
                        if self._process is None or self._process.returncode is not None:
                            raise RuntimeError("Neve Image 3: worker interrompido\n" + "\n".join(self._log_tail[-20:]))
                        response = await client.get(f"/history/{self._prompt_id}")
                        response.raise_for_status()
                        history = response.json().get(self._prompt_id)
                        if history:
                            if history.get("status", {}).get("status_str") == "error":
                                raise worker_error("Neve Image 3", history["status"])
                            images = history.get("outputs", {}).get("13", {}).get("images", [])
                            if images:
                                output = images[0]
                                response = await client.get("/view", params=output)
                                response.raise_for_status()
                                with Image.open(io.BytesIO(response.content)) as image:
                                    if image.size != (width, height):
                                        raise RuntimeError("Neve Image 3 retornou dimensoes inesperadas")
                                if details is not None:
                                    details.update(model="MiniMax-H3-Image", quantization="W4A8", steps=6, width=width, height=height)
                                await report(100)
                                return "data:image/png;base64," + base64.b64encode(response.content).decode()
                        await asyncio.sleep(0.5)
                raise RuntimeError("Neve Image 3 excedeu o tempo de geracao")
            finally:
                if progress_task:
                    progress_task.cancel()
                    await asyncio.gather(progress_task, return_exceptions=True)
                await self._stop()
                for filename in uploaded:
                    path = (ROOT / "input" / filename).resolve()
                    if path.is_relative_to((ROOT / "input").resolve()):
                        path.unlink(missing_ok=True)
                if output:
                    path = (ROOT / "output" / output.get("subfolder", "") / output["filename"]).resolve()
                    if path.is_relative_to((ROOT / "output").resolve()):
                        path.unlink(missing_ok=True)

    async def _watch_progress(self, base, prompt_id, progress):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(base.replace("http://", "ws://") + "/ws", heartbeat=30) as ws:
                    async for event in ws:
                        if event.type == aiohttp.WSMsgType.TEXT:
                            message = event.json()
                            data = message.get("data", {})
                            if message.get("type") == "progress" and data.get("prompt_id") == prompt_id and data.get("max"):
                                await progress(34 + int(60 * data["value"] / data["max"]))
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass  # Result polling remains authoritative if the progress connection fails.


neve_image_3_runtime = NeveImage3Runtime()
