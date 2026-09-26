"""Isolated ComfyUI runtime for Neve Image 2 Fast (Qwen Image 2.1 + Viggle)."""

import asyncio
import base64
import io
import logging
import os
import random
import re
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
RUNTIME_REVISION = "neve-image-2s-viggle-0.2.1-v2"
COMFY_COMMIT = "b0f4b7b294ce482a2e071d9d762c133d38c7aa07"
GGUF_COMMIT = "373048b8403a7820620065210a691263d4da0a61"
VIGGLE_REPO = "Viggle/Qwen-Image-2.1-viggle-turbo"
MODEL_REPO = "abenzerps/Qwen-Image-2.1-Uncensored-GGUF"
MODEL_FILE = "qwen-image-2.1-UC-Q4_K_M.gguf"
ENCODER_REPO = "Comfy-Org/Qwen-Image-2.1"
ENCODER_FILE = "qwen3vl_8b_int8_convrot.safetensors"
VAE_FILE = "qwen_image_2.1_vae_bf16.safetensors"
LORA_FILE = "Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors"
SIGMAS = "1.0, 0.9375, 0.875, 0.75, 0.5, 0.25"
DIMENSIONS = {
    "1:1": (1152, 1152),
    "16:9": (1216, 704),
    "9:16": (704, 1216),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
}


def _style_only_references(prompt: str, count: int) -> set[int]:
    if count < 2:
        return set()
    forward = re.finditer(
        r"\b(?:estilo|style)\b"
        r"(?:\s+(?:visual|artístico|artistico|deve|ser|seja|como|igual|ao|à|a|o|da|de|do|"
        r"the|should|be|like|as|from|of|in|na|no|pela|pelo|referência|referencia|reference)){0,8}"
        r"\s+(?:imagem|image|foto|picture|referencia|reference)\s*#?\s*(\d+)\b",
        prompt,
        flags=re.IGNORECASE | re.DOTALL,
    )
    reverse = re.finditer(
        r"\b(?:imagem|image|foto|picture|referencia|reference)\s*#?\s*(\d+)\s+"
        r"(?:(?:como|as|para|for|de|do|da|is|e|é)\s+){0,2}"
        r"(?:(?:referência|referencia|reference)\s+(?:de|for)\s+)?(?:estilo|style)\b",
        prompt,
        flags=re.IGNORECASE | re.DOTALL,
    )
    indexes = {int(match.group(1)) - 1 for match in (*forward, *reverse) if 1 <= int(match.group(1)) <= count}
    return indexes if len(indexes) < count else set()


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
            raise RuntimeError("Pacote ComfyUI invalido para Neve Image 2 Fast")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(source_dirs[0]), str(destination))


def _download_node() -> None:
    CUSTOM_NODES_DIR.mkdir(parents=True, exist_ok=True)
    target = CUSTOM_NODES_DIR / "viggle_turbo.py"
    url = f"https://huggingface.co/{VIGGLE_REPO}/resolve/main/comfyui/viggle_turbo.py"
    request = urllib.request.Request(url, headers={"User-Agent": "NeveAI/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        source = response.read()
    if b"ViggleTurboSigmas" not in source or b"ViggleTurboLora" not in source:
        raise RuntimeError("No Viggle Turbo nao reconhecido")
    target.write_bytes(source)


class NeveImage2SRuntime:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._log_task: Optional[asyncio.Task] = None
        self._log_tail: list[str] = []
        self._port: Optional[int] = None
        self._prompt_id: Optional[str] = None

    @property
    def is_installed(self) -> bool:
        try:
            return (
                MARKER.read_text(encoding="utf-8").strip() == RUNTIME_REVISION
                and (COMFY_DIR / "main.py").is_file()
                and _python().is_file()
                and (CUSTOM_NODES_DIR / "viggle_turbo.py").is_file()
                and (CUSTOM_NODES_DIR / "ComfyUI-GGUF" / "__init__.py").is_file()
            )
        except OSError:
            return False

    @property
    def models_ready(self) -> bool:
        files = (
            MODELS_DIR / "diffusion_models" / MODEL_FILE,
            MODELS_DIR / "text_encoders" / ENCODER_FILE,
            MODELS_DIR / "vae" / VAE_FILE,
            MODELS_DIR / "loras" / LORA_FILE,
        )
        return all(path.is_file() and path.stat().st_size > 1024 for path in files)

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
                log.debug("Neve Image 2 Fast setup: %s", decoded)
            code = await process.wait()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        if code:
            raise RuntimeError("Falha ao instalar Neve Image 2 Fast:\n" + "\n".join(output))

    async def _install(self, progress: ProgressCallback) -> None:
        if self.is_installed:
            return
        if os.name != "nt":
            raise RuntimeError("Neve Image 2 Fast via ComfyUI requer Windows nesta instalacao.")
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
        if not (CUSTOM_NODES_DIR / "viggle_turbo.py").is_file():
            await asyncio.to_thread(_download_node)
        if not _python().is_file():
            await self._command([sys.executable, "-m", "uv", "venv", str(RUNTIME_DIR), "--python", sys.executable])
        await progress(8)
        await self._command([
            sys.executable, "-m", "uv", "pip", "install", "--python", str(_python()),
            "torch==2.11.0", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu130",
        ])
        await self._command([
            sys.executable, "-m", "uv", "pip", "install", "--python", str(_python()),
            "-r", str(COMFY_DIR / "requirements.txt"), "gguf>=0.17,<1", "huggingface_hub>=0.34,<2",
        ])
        await self._command([
            str(_python()), "-c",
            "import torch, gguf; assert torch.cuda.is_available(), 'CUDA indisponivel'",
        ])
        MARKER.write_text(RUNTIME_REVISION, encoding="utf-8")

    async def _models(self, progress: ProgressCallback) -> None:
        if self.models_ready:
            return
        await progress(12)
        script = f"""
from huggingface_hub import hf_hub_download
items = {[
    (MODEL_REPO, MODEL_FILE, 'diffusion_models'),
    (ENCODER_REPO, f'text_encoders/{ENCODER_FILE}', ''),
    (ENCODER_REPO, f'vae/{VAE_FILE}', ''),
    (VIGGLE_REPO, LORA_FILE, 'loras'),
]!r}
for repo, filename, subdir in items:
    root = {str(MODELS_DIR)!r}
    if subdir:
        root = __import__('os').path.join(root, subdir)
    hf_hub_download(repo_id=repo, filename=filename, local_dir=root)
"""
        await self._command([str(_python()), "-c", script])
        if not self.models_ready:
            raise RuntimeError("Os arquivos de Neve Image 2 Fast nao foram baixados por completo.")
        await progress(18)

    @staticmethod
    def build_workflow(prompt: str, width: int, height: int, refs: list[str], seed: int) -> dict:
        if not 1 <= len(refs) + 1 <= 4:
            raise ValueError("Neve Image 2 Fast aceita no maximo tres imagens de referencia.")
        if refs:
            from neveai.routers.stable_diffusion import _normalize_qwen_reference_tokens

            prompt = _normalize_qwen_reference_tokens(prompt, len(refs))
            prompt = (
                "Follow the user's assignment of subject, pose, background and visual style to each numbered image exactly. "
                "Never substitute a subject from an image assigned only as a style reference. "
                f"User request: {prompt}"
            )
        workflow = {
            "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": MODEL_FILE}},
            "2": {"class_type": "ViggleTurboLora", "inputs": {"model": ["1", 0], "lora_name": LORA_FILE, "strength": 1.0}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": ENCODER_FILE, "type": "qwen_image", "device": "default"}},
            "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_FILE}},
            "5": {"class_type": "TextEncodeQwenImage21", "inputs": {"clip": ["3", 0], "vae": ["4", 0], "prompt": prompt, "negative_prompt": "", "resolution": 1024}},
            "6": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "7": {"class_type": "BasicGuider", "inputs": {"model": ["2", 0], "conditioning": ["5", 0]}},
            "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "10": {"class_type": "ViggleTurboSigmas", "inputs": {"latent": ["6", 0], "nodes": SIGMAS}},
            "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["8", 0], "guider": ["7", 0], "sampler": ["9", 0], "sigmas": ["10", 0], "latent_image": ["6", 0]}},
            "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["4", 0]}},
            "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": "neve_image_2s"}},
        }
        if refs:
            workflow["14"] = {"class_type": "QwenImage21Cache", "inputs": {"model": ["2", 0], "device": "auto", "dtype": "default"}}
            workflow["7"]["inputs"]["model"] = ["14", 0]
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
            log.debug("Neve Image 2 Fast ComfyUI: %s", decoded)

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
        args = [
            str(_python()), str(COMFY_DIR / "main.py"), "--listen", "127.0.0.1",
            "--port", str(self._port), "--base-directory", str(IMAGE_ROOT),
            "--input-directory", str(INPUT_DIR), "--output-directory", str(OUTPUT_DIR),
            "--temp-directory", str(TEMP_DIR), "--disable-auto-launch",
            "--preview-method", "none", "--cache-none", "--reserve-vram", "0.75",
            "--disable-metadata",
        ]
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
        raise RuntimeError("ComfyUI do Neve Image 2 Fast nao respondeu.")

    async def run(
        self, prompt: str, resolution: str, references: list[str], user_id: Optional[str],
        progress: ProgressCallback, dimensions: Optional[DimensionsCallback] = None,
    ) -> str:
        if len(references) > 3:
            raise ValueError("Neve Image 2 Fast aceita ate tres imagens de referencia.")
        if not prompt.strip():
            raise ValueError("Descreva a imagem que deseja criar.")
        if os.name == "nt":
            from neveai.routers.stable_diffusion import (
                QWEN_IMAGE_21_REPO,
                QWEN_IMAGE_21_STEPS,
                _preferred_sd_cpp_windows_backend,
                _sd_pipeline,
            )

            if _preferred_sd_cpp_windows_backend() == "vulkan":
                width, height = DIMENSIONS.get(resolution, DIMENSIONS["1:1"])
                log.warning("Neve Image 2 Fast: modo AMD Vulkan usa Qwen Image 2.1 sem o LoRA Viggle de 6 passos")
                return await _sd_pipeline.run(
                    model_id=QWEN_IMAGE_21_REPO,
                    hf_token=None,
                    quality="qwen_image_2_1",
                    style="none",
                    resolution=resolution,
                    prompt=prompt,
                    width=width,
                    height=height,
                    steps=QWEN_IMAGE_21_STEPS,
                    guidance_scale=1.0,
                    init_image_references=references,
                    user_id=user_id,
                    progress_callback=progress,
                    dimensions_callback=dimensions,
                )
        async with self._lock:
            uploaded_refs: list[str] = []
            try:
                await self._install(progress)
                await self._models(progress)
                base = await self._start(progress)
                async with httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(30, read=120, write=120, pool=30)) as client:
                    from neveai.routers.stable_diffusion import _read_image_reference_bytes

                    width, height = DIMENSIONS.get(resolution, DIMENSIONS["1:1"])
                    if dimensions is not None:
                        await dimensions(width, height)
                    refs = []
                    style_only = _style_only_references(prompt, len(references))
                    for index, reference in enumerate(references):
                        raw = await asyncio.to_thread(_read_image_reference_bytes, reference, user_id)
                        from PIL import Image, ImageFilter, ImageOps

                        image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
                        if index in style_only:
                            image = image.filter(ImageFilter.GaussianBlur(max(image.size) * 0.05))
                        image_bytes = io.BytesIO()
                        image.save(image_bytes, format="PNG")
                        response = await client.post(
                            "/upload/image",
                            files={"image": (f"neve_2s_{random.getrandbits(64):016x}.png", image_bytes.getvalue(), "image/png")},
                            data={"type": "input", "overwrite": "false"},
                        )
                        response.raise_for_status()
                        filename = response.json()["name"]
                        refs.append(filename)
                        uploaded_refs.append(filename)
                    await progress(28)
                    workflow = self.build_workflow(prompt, width, height, refs, random.getrandbits(63))
                    client_id = f"neve-image-2s-{random.getrandbits(64):016x}"
                    response = await client.post("/prompt", json={"prompt": workflow, "client_id": client_id})
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("node_errors"):
                        raise RuntimeError(f"Workflow Neve Image 2 Fast invalido: {payload['node_errors']}")
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
                            for _ in range(1800):
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
                                                    last_progress = max(last_progress, min(94, 40 + int(54 * item["value"] / item["max"])))
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
                                    raise RuntimeError(f"Neve Image 2 Fast falhou: {status.get('messages')}")
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
                                                f"Neve Image 2 Fast retornou {generated.width}x{generated.height}; esperado {width}x{height}."
                                            )
                                    output_path = (OUTPUT_DIR / item.get("subfolder", "") / item["filename"]).resolve()
                                    if output_path.is_relative_to(OUTPUT_DIR.resolve()):
                                        output_path.unlink(missing_ok=True)
                                    await progress(99)
                                    return "data:image/png;base64," + base64.b64encode(response.content).decode("ascii")
                            raise RuntimeError("Neve Image 2 Fast excedeu o tempo limite.")
                        finally:
                            if websocket is not None:
                                await websocket.close()
            finally:
                await self._stop()
                for filename in uploaded_refs:
                    path = (INPUT_DIR / filename).resolve()
                    if path.is_relative_to(INPUT_DIR.resolve()):
                        path.unlink(missing_ok=True)


neve_image_2s_runtime = NeveImage2SRuntime()
