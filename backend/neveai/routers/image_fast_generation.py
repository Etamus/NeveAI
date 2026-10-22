"""Isolated Qwen Image 2.1 Turbo runtime for Neve Image 2."""

import asyncio
import base64
import hashlib
import io
import logging
import math
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Awaitable, Callable, Optional

import aiohttp
import httpx

from neveai.config import CACHE_DIR
from neveai.utils.image_memory import cpu_image_requested, cpu_image_size, is_image_memory_error, monotonic_progress, worker_error

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int], Awaitable[None]]
DimensionsCallback = Callable[[int, int], Awaitable[None]]

IMAGE_ROOT = CACHE_DIR / "image_fast_generation"
COMFY_DIR = IMAGE_ROOT / "ComfyUI"
RUNTIME_DIR = IMAGE_ROOT / "runtime"
MODELS_DIR = IMAGE_ROOT / "models"
CUSTOM_NODES_DIR = IMAGE_ROOT / "custom_nodes"
INPUT_DIR = IMAGE_ROOT / "input"
OUTPUT_DIR = IMAGE_ROOT / "output"
TEMP_DIR = IMAGE_ROOT / "temp"
MARKER = IMAGE_ROOT / ".neve-image-2s-ready"
RUNTIME_REVISION = "neve-image-2-turbo-8step-v1-comfy-0.38"
COMFY_COMMIT = "6b747c0428c343e1417219641db93a4fb7cb69ae"
GGUF_COMMIT = "373048b8403a7820620065210a691263d4da0a61"
MODEL_REPO = "Comfy-Org/Qwen-Image-2.1"
MODEL_REVISION = "a8342359c61979b06a8dafb1a47991fe1f30e994"
MODEL_FILE = "qwen_image_2.1_turbo_int8_convrot.safetensors"
ENCODER_REPO = "Comfy-Org/Qwen-Image-2.1"
ENCODER_FILE = "qwen3vl_8b_int8_convrot.safetensors"
VAE_FILE = "qwen_image_2.1_vae_bf16.safetensors"
SIGMAS = "1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568, 0"
TURBO_STEPS = 8
MAX_REFERENCES = 10
GGUF_MODEL_FILE = "qwen-image-2.1-turbo-Q4_K_M.gguf"
GGUF_MODEL_BYTES = 4199565120
GGUF_MODEL_SHA256 = "8940e8b522af886e0c0f5afddf720e82dd223cb9a43580b5f61c4d740452ac20"
MODEL_ASSETS = (
    ("diffusion_models/" + MODEL_FILE, 7256787829, "8144a0182964aa8403ad6dbc011db837304167d235161b9aabaa8532e967314c"),
    ("text_encoders/" + ENCODER_FILE, 9350798360, "8bfd0f6e12abf2d2d697ecc888e5e90b0d6741d6708f05799f53afa560452e8f"),
    ("vae/" + VAE_FILE, 675509688, "bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9"),
)
DIMENSIONS = {
    "1:1": (1152, 1152),
    "16:9": (1216, 704),
    "9:16": (704, 1216),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_size(width: int, height: int, index: int, count: int) -> tuple[int, int]:
    if width < 1 or height < 1:
        raise ValueError("Imagem de referencia invalida")
    budget = 1152 * 1152
    if index:
        budget = min(budget, 2 * budget / max(1, count - 1))
    scale = min(math.sqrt(budget / (width * height)), 1536 / max(width, height))
    return tuple(max(32, round(side * scale / 32) * 32) for side in (width, height))


def _encode_reference_png(raw: bytes, index: int, count: int, *, cpu_mode: bool = False) -> tuple[bytes, tuple[int, int]]:
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    size = _reference_size(*image.size, index, count)
    if cpu_mode:
        size = cpu_image_size(*size, max_side=512 if index == 0 else 256)
    if size != image.size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    encoded = io.BytesIO()
    image.save(encoded, format="PNG", compress_level=3)
    return encoded.getvalue(), size


def _python() -> Path:
    return RUNTIME_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _process_kwargs() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def _replace_archive(url: str, destination: Path) -> None:
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=IMAGE_ROOT) as temporary:
        root = Path(temporary)
        archive_path = root / "source.zip"
        request = urllib.request.Request(url, headers={"User-Agent": "NeveAI/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, archive_path.open("wb") as output:
            shutil.copyfileobj(response, output)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(root / "extracted")
        source_dirs = [path for path in (root / "extracted").iterdir() if path.is_dir()]
        if len(source_dirs) != 1:
            raise RuntimeError("Pacote ComfyUI invalido para Neve Image 2")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(source_dirs[0]), str(destination))


class NeveImage2SRuntime:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._gguf_mode = self._cpu_mode = self._memory_saver = False
        self._process: Optional[asyncio.subprocess.Process] = None
        self._log_task: Optional[asyncio.Task] = None
        self._log_tail: list[str] = []
        self._port: Optional[int] = None
        self._prompt_id: Optional[str] = None
        self._verified_assets: dict[Path, tuple[int, int]] = {}

    @property
    def is_installed(self) -> bool:
        try:
            return (
                MARKER.read_text(encoding="utf-8").strip() in {
                    RUNTIME_REVISION, "neve-image-2s-viggle-0.2.1-v3-comfy-0.38"
                }
                and (COMFY_DIR / "main.py").is_file()
                and _python().is_file()
                and (CUSTOM_NODES_DIR / "ComfyUI-GGUF" / "__init__.py").is_file()
            )
        except OSError:
            return False

    @property
    def models_ready(self) -> bool:
        return all(
            (MODELS_DIR / filename).is_file()
            and (MODELS_DIR / filename).stat().st_size == size
            for filename, size, _ in MODEL_ASSETS
        )

    async def _command(self, args: list[str]) -> None:
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            **_process_kwargs(),
        )
        output: list[str] = []
        try:
            while line := await process.stdout.readline():
                decoded = line.decode("utf-8", errors="replace").rstrip()
                output.append(decoded)
                if len(output) > 30:
                    output.pop(0)
                log.debug("Neve Image 2 setup: %s", decoded)
            code = await process.wait()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        if code:
            raise RuntimeError("Falha ao instalar Neve Image 2:\n" + "\n".join(output))

    async def _install(self, progress: ProgressCallback, *, cpu_mode: bool = False) -> None:
        if self.is_installed:
            if MARKER.read_text(encoding="utf-8").strip() != RUNTIME_REVISION:
                MARKER.write_text(RUNTIME_REVISION, encoding="utf-8")
            return
        if os.name != "nt":
            raise RuntimeError("Neve Image 2 via ComfyUI requer Windows nesta instalacao.")
        IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
        await progress(2)
        check = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "uv", "--version",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            **_process_kwargs(),
        )
        if await check.wait():
            await self._command([sys.executable, "-m", "pip", "install", "uv>=0.8,<1"])
        if not (COMFY_DIR / "main.py").is_file():
            await asyncio.to_thread(
                _replace_archive,
                f"https://github.com/Comfy-Org/ComfyUI/archive/{COMFY_COMMIT}.zip",
                COMFY_DIR,
            )
        await progress(5)
        gguf_revision_file = CUSTOM_NODES_DIR / "ComfyUI-GGUF" / ".neve-revision"
        if not gguf_revision_file.is_file() or gguf_revision_file.read_text(encoding="utf-8").strip() != GGUF_COMMIT:
            await asyncio.to_thread(
                _replace_archive,
                f"https://github.com/leejet/ComfyUI-GGUF/archive/{GGUF_COMMIT}.zip",
                CUSTOM_NODES_DIR / "ComfyUI-GGUF",
            )
            gguf_revision_file.write_text(GGUF_COMMIT, encoding="utf-8")
        if not _python().is_file():
            await self._command([sys.executable, "-m", "uv", "venv", str(RUNTIME_DIR), "--python", sys.executable])
        await progress(8)
        await self._command([
            sys.executable, "-m", "uv", "pip", "install", "--python", str(_python()),
            "torch==2.11.0", "torchvision", "--index-url",
            "https://download.pytorch.org/whl/cpu" if self._cpu_mode or cpu_mode else "https://download.pytorch.org/whl/cu130",
        ])
        await self._command([
            sys.executable, "-m", "uv", "pip", "install", "--python", str(_python()),
            "-r", str(COMFY_DIR / "requirements.txt"), "gguf>=0.17,<1", "huggingface_hub>=0.34,<2",
        ])
        await self._command([
            str(_python()), "-c",
            "import torch, gguf; " + ("" if self._cpu_mode or cpu_mode else "assert torch.cuda.is_available(), 'CUDA indisponivel'"),
        ])
        MARKER.write_text(RUNTIME_REVISION, encoding="utf-8")

    async def _models(self, progress: ProgressCallback) -> None:
        await progress(12)
        from huggingface_hub import hf_hub_download

        assets = MODEL_ASSETS[1:] if self._gguf_mode else MODEL_ASSETS
        pending = []
        for filename, size, sha in assets:
            target = MODELS_DIR / filename
            if not target.exists():
                await asyncio.to_thread(
                    hf_hub_download, repo_id=MODEL_REPO, filename=filename,
                    revision=MODEL_REVISION, local_dir=str(MODELS_DIR),
                )
            if not target.is_file() or target.stat().st_size != size:
                raise RuntimeError(f"Neve Image 2 Turbo: arquivo incompleto: {target.name}")
            signature = (size, target.stat().st_mtime_ns)
            if self._verified_assets.get(target) != signature:
                pending.append((target, sha, signature))

        # Bound disk readers and retain the full checksum before starting the worker.
        verification_slots = asyncio.Semaphore(2)
        async def verify(target, sha, signature):
            async with verification_slots:
                digest = await asyncio.to_thread(_sha256, target)
            if digest != sha:
                raise RuntimeError(f"Neve Image 2 Turbo: integridade invalida: {target.name}")
            self._verified_assets[target] = signature

        results = await asyncio.gather(*(verify(*item) for item in pending), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        if self._gguf_mode:
            from neveai.routers.stable_diffusion import QWEN_IMAGE_TURBO_REPO, QWEN_IMAGE_TURBO_REVISION

            target = MODELS_DIR / "diffusion_models" / GGUF_MODEL_FILE
            if not target.is_file():
                await asyncio.to_thread(hf_hub_download, repo_id=QWEN_IMAGE_TURBO_REPO,
                                       revision=QWEN_IMAGE_TURBO_REVISION, filename=GGUF_MODEL_FILE,
                                       local_dir=str(target.parent))
            if target.stat().st_size != GGUF_MODEL_BYTES:
                raise RuntimeError("Neve Image 2 Turbo GGUF: arquivo incompleto")
            signature = (target.stat().st_size, target.stat().st_mtime_ns)
            if self._verified_assets.get(target) != signature:
                if await asyncio.to_thread(_sha256, target) != GGUF_MODEL_SHA256:
                    raise RuntimeError("Neve Image 2 Turbo GGUF: integridade invalida")
                self._verified_assets[target] = signature
        await progress(18)

    @staticmethod
    def build_workflow(prompt: str, width: int, height: int, refs: list[str], seed: int) -> dict:
        if len(refs) > MAX_REFERENCES:
            raise ValueError("Neve Image 2 aceita no maximo dez imagens de referencia.")
        if refs:
            from neveai.routers.stable_diffusion import _normalize_qwen_reference_tokens

            prompt = _normalize_qwen_reference_tokens(prompt, len(refs))
            prompt = (
                "Follow the user's assignment of subject, pose, background and visual style to each numbered image exactly. "
                "Never substitute a subject from an image assigned only as a style reference. "
                f"User request: {prompt}"
            )
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": MODEL_FILE, "weight_dtype": "default"}},
            "2": {"class_type": "QwenImage21Cache", "inputs": {"model": ["1", 0], "device": "auto", "dtype": "default"}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": ENCODER_FILE, "type": "qwen_image", "device": "default"}},
            "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_FILE}},
            "5": {"class_type": "TextEncodeQwenImage21", "inputs": {"clip": ["3", 0], "vae": ["4", 0], "prompt": prompt, "negative_prompt": "", "resolution": 0 if refs else 1024}},
            "6": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "7": {"class_type": "BasicGuider", "inputs": {"model": ["2", 0], "conditioning": ["5", 0]}},
            "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "10": {"class_type": "ManualSigmas", "inputs": {"sigmas": SIGMAS}},
            "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["8", 0], "guider": ["7", 0], "sampler": ["9", 0], "sigmas": ["10", 0], "latent_image": ["5", 2] if refs else ["6", 0]}},
            "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["4", 0]}},
            "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": "neve_image_2s"}},
        }
        for index, filename in enumerate(refs, 1):
            node_id = str(14 + index)
            workflow[node_id] = {"class_type": "LoadImage", "inputs": {"image": filename}}
            workflow["5"]["inputs"][f"images.image_{index}"] = [node_id, 0]
        return workflow

    async def _capture_logs(self, process: asyncio.subprocess.Process) -> None:
        while line := await process.stdout.readline():
            decoded = line.decode("utf-8", errors="replace").rstrip()
            self._log_tail.append(decoded)
            if len(self._log_tail) > 100:
                self._log_tail.pop(0)
            log.debug("Neve Image 2 ComfyUI: %s", decoded)

    async def _stop(self) -> None:
        process, self._process = self._process, None
        self._port = None
        self._prompt_id = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        if self._log_task is not None:
            try:
                await asyncio.wait_for(self._log_task, timeout=2)
            except asyncio.TimeoutError:
                self._log_task.cancel()
                await asyncio.gather(self._log_task, return_exceptions=True)
            self._log_task = None

    async def cancel(self) -> None:
        if self._port is not None:
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    await client.post(f"http://127.0.0.1:{self._port}/interrupt")
            except httpx.HTTPError:
                pass
        await self._stop()

    async def _start(self, progress: ProgressCallback) -> str:
        for directory in (INPUT_DIR, OUTPUT_DIR, TEMP_DIR):
            directory.mkdir(parents=True, exist_ok=True)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            self._port = int(listener.getsockname()[1])
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        self._log_tail.clear()
        args = self._comfy_command()
        self._process = await asyncio.create_subprocess_exec(
            *args, cwd=str(COMFY_DIR), env=env, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, **_process_kwargs(),
        )
        self._log_task = asyncio.create_task(self._capture_logs(self._process))
        base = f"http://127.0.0.1:{self._port}"
        async with httpx.AsyncClient(timeout=2) as client:
            for attempt in range(240):
                if self._process.returncode is not None:
                    raise RuntimeError("ComfyUI 2S encerrou:\n" + "\n".join(self._log_tail[-25:]))
                try:
                    response = await client.get(f"{base}/system_stats")
                    if response.is_success:
                        await progress(23)
                        return base
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
        raise RuntimeError("ComfyUI do Neve Image 2 nao respondeu.")

    def _comfy_command(self) -> list[str]:
        return [
            str(_python()), str(COMFY_DIR / "main.py"), "--listen", "127.0.0.1",
            "--port", str(self._port), "--base-directory", str(IMAGE_ROOT),
            "--input-directory", str(INPUT_DIR), "--output-directory", str(OUTPUT_DIR),
            "--temp-directory", str(TEMP_DIR), "--disable-auto-launch",
            "--preview-method", "none", "--cache-none", "--reserve-vram", "0.75",
            "--disable-metadata",
            *(["--cpu"] if self._cpu_mode else ["--lowvram"] if self._memory_saver else []),
        ]

    def _encode_reference(self, raw: bytes, index: int, count: int, *, cpu_mode: bool = False):
        return _encode_reference_png(raw, index, count, cpu_mode=cpu_mode)

    def _output_dimensions(self, width: int, height: int) -> tuple[int, int]:
        return width, height

    def _finalize_image(self, data: bytes) -> bytes:
        return data

    async def run(
        self, prompt: str, resolution: str, references: list[str], user_id: Optional[str],
        progress: ProgressCallback, dimensions: Optional[DimensionsCallback] = None,
    ) -> str:
        async with self._request_lock:
            from neveai.routers.stable_diffusion import _preferred_sd_cpp_windows_backend

            cpu = os.name == "nt" and cpu_image_requested(await asyncio.to_thread(_preferred_sd_cpp_windows_backend))
            plans = [(True, True, True)] if cpu else [(False, False, False), (True, False, True), (True, True, True)]
            report = monotonic_progress(progress)
            seed = random.getrandbits(63)
            for index, (gguf, cpu_mode, saver) in enumerate(plans):
                try:
                    return await self._run_once(prompt, resolution, references, user_id, report, dimensions,
                                                gguf=gguf, cpu_mode=cpu_mode, memory_saver=saver, seed=seed)
                except Exception as exc:
                    if not is_image_memory_error(exc) or index == len(plans) - 1:
                        raise
                    log.warning("Neve Image 2: recuperacao de memoria, tentativa %s: %s", index + 2, exc)

    async def _run_once(
        self, prompt: str, resolution: str, references: list[str], user_id: Optional[str],
        progress: ProgressCallback, dimensions: Optional[DimensionsCallback] = None, *,
        gguf: bool = False, cpu_mode: bool = False, memory_saver: bool = False, seed: Optional[int] = None,
    ) -> str:
        if len(references) > MAX_REFERENCES:
            raise ValueError("Neve Image 2 aceita ate dez imagens de referencia.")
        if not prompt.strip():
            raise ValueError("Descreva a imagem que deseja criar.")
        if os.name == "nt":
            from neveai.routers.stable_diffusion import (
                QWEN_IMAGE_TURBO_REPO,
                QWEN_IMAGE_FAST_AMD_STEPS,
                QWEN_IMAGE_2_FAST_AMD_QUALITY,
                _preferred_sd_cpp_windows_backend,
                _sd_pipeline,
            )

            if not cpu_mode and await asyncio.to_thread(_preferred_sd_cpp_windows_backend) == "vulkan":
                width, height = DIMENSIONS.get(resolution, DIMENSIONS["1:1"])
                log.info("Neve Image 2: usando Qwen Image 2.1 Turbo via AMD Vulkan")
                return await _sd_pipeline.run(
                    model_id=QWEN_IMAGE_TURBO_REPO,
                    hf_token=None,
                    quality=QWEN_IMAGE_2_FAST_AMD_QUALITY,
                    style="none",
                    resolution=resolution,
                    prompt=prompt,
                    width=width,
                    height=height,
                    steps=QWEN_IMAGE_FAST_AMD_STEPS,
                    guidance_scale=1.0,
                    init_image_references=references,
                    user_id=user_id,
                    progress_callback=progress,
                    dimensions_callback=dimensions,
                )
        async with self._lock:
            uploaded_refs: list[str] = []
            self._gguf_mode, self._cpu_mode, self._memory_saver = gguf, cpu_mode, memory_saver
            try:
                await self._install(progress)
                await self._models(progress)
                base = await self._start(progress)
                async with httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(30, read=120, write=120, pool=30)) as client:
                    from neveai.routers.stable_diffusion import _read_image_reference_bytes

                    width, height = DIMENSIONS.get(resolution, DIMENSIONS["1:1"])
                    if cpu_mode:
                        width, height = cpu_image_size(width, height)
                    if dimensions is not None and not references:
                        await dimensions(width, height)
                    refs = []
                    for index, reference in enumerate(references):
                        raw = await asyncio.to_thread(_read_image_reference_bytes, reference, user_id)
                        image_bytes, size = await asyncio.to_thread(
                            self._encode_reference, raw, index, len(references), cpu_mode=cpu_mode,
                        )
                        if index == 0:
                            width, height = size
                        response = await client.post(
                            "/upload/image",
                            files={"image": (f"neve_2s_{random.getrandbits(64):016x}.png", image_bytes, "image/png")},
                            data={"type": "input", "overwrite": "false"},
                        )
                        response.raise_for_status()
                        filename = response.json()["name"]
                        refs.append(filename)
                        uploaded_refs.append(filename)
                    if dimensions is not None and references:
                        await dimensions(*self._output_dimensions(width, height))
                    await progress(28)
                    workflow = self.build_workflow(prompt, width, height, refs, seed if seed is not None else random.getrandbits(63))
                    if gguf:
                        workflow["1"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": GGUF_MODEL_FILE}}
                    if memory_saver:
                        workflow["2"]["inputs"]["device"] = "cpu"
                    client_id = f"neve-image-2s-{random.getrandbits(64):016x}"
                    response = await client.post("/prompt", json={"prompt": workflow, "client_id": client_id})
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("node_errors"):
                        raise RuntimeError(f"Workflow Neve Image 2 invalido: {payload['node_errors']}")
                    self._prompt_id = str(payload.get("prompt_id") or "")
                    if not self._prompt_id:
                        raise RuntimeError("ComfyUI nao retornou identificador da imagem.")
                    await progress(34)
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None)) as session:
                        websocket_url = base.replace("http://", "ws://")
                        try:
                            websocket = await session.ws_connect(f"{websocket_url}/ws?clientId={client_id}", heartbeat=30)
                        except Exception:
                            websocket = None
                        try:
                            last_progress = 34
                            for _ in range(10800 if cpu_mode else 1800):
                                if self._process is None or self._process.returncode is not None:
                                    raise RuntimeError("ComfyUI 2S parou durante a geracao:\n" + "\n".join(self._log_tail[-25:]))
                                if websocket is not None:
                                    try:
                                        event = await asyncio.wait_for(websocket.receive(), timeout=1)
                                        if event.type == aiohttp.WSMsgType.TEXT:
                                            data = event.json()
                                            if data.get("type") == "progress":
                                                item = data.get("data") or {}
                                                if item.get("prompt_id") == self._prompt_id and item.get("max"):
                                                    completed = item["value"]
                                                    last_progress = max(last_progress, min(94, 40 + int(54 * completed / item["max"])))
                                    except asyncio.TimeoutError:
                                        pass
                                else:
                                    await asyncio.sleep(1)
                                await progress(last_progress)
                                result = await client.get(f"/history/{self._prompt_id}")
                                result.raise_for_status()
                                history = result.json().get(self._prompt_id)
                                if not history:
                                    continue
                                status = history.get("status") or {}
                                if status.get("status_str") == "error":
                                    raise worker_error("Neve Image 2", status)
                                outputs = history.get("outputs") or {}
                                images = outputs.get("13", {}).get("images") or []
                                if images:
                                    item = images[0]
                                    response = await client.get("/view", params={"filename": item["filename"], "subfolder": item.get("subfolder", ""), "type": item.get("type", "output")})
                                    response.raise_for_status()
                                    from PIL import Image

                                    with Image.open(io.BytesIO(response.content)) as generated:
                                        if generated.size != (width, height):
                                            raise RuntimeError(
                                                f"Neve Image 2 retornou {generated.width}x{generated.height}; esperado {width}x{height}."
                                            )
                                    output_path = (OUTPUT_DIR / item.get("subfolder", "") / item["filename"]).resolve()
                                    if output_path.is_relative_to(OUTPUT_DIR.resolve()):
                                        output_path.unlink(missing_ok=True)
                                    await progress(99)
                                    image_data = await asyncio.to_thread(self._finalize_image, response.content)
                                    return "data:image/png;base64," + base64.b64encode(image_data).decode("ascii")
                            raise RuntimeError("Neve Image 2 excedeu o tempo limite.")
                        finally:
                            if websocket is not None:
                                await websocket.close()
            finally:
                await self._stop()
                self._gguf_mode = self._cpu_mode = self._memory_saver = False
                for filename in uploaded_refs:
                    path = (INPUT_DIR / filename).resolve()
                    if path.is_relative_to(INPUT_DIR.resolve()):
                        path.unlink(missing_ok=True)


neve_image_2s_runtime = NeveImage2SRuntime()
