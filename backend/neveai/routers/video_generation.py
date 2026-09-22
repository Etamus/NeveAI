"""Local MiniMax H3 video generation through an isolated ComfyUI worker."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import shutil
import socket
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections import deque
from pathlib import Path
from typing import Awaitable, Callable, Optional

import aiohttp
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from neveai.config import CACHE_DIR
from neveai.constants import ERROR_MESSAGES
from neveai.utils.access_control import has_permission
from neveai.utils.auth import get_verified_user

log = logging.getLogger(__name__)
router = APIRouter()

ProgressCallback = Callable[[str, Optional[int]], Awaitable[None]]

COMFYUI_COMMIT = "b0f4b7b294ce482a2e071d9d762c133d38c7aa07"
CLIPPROJ_COMMIT = "c01ba8fb8f41b4f2094dbd0b185cdc238fb6134c"
TURBO_NODE_COMMIT = "4274783a23afcfdbea3b4876cb79effd6c510785"
VIDEO_RUNTIME_REVISION = "neve-minimax-h3-fl2va-w4a8-v1"

VIDEO_ROOT = CACHE_DIR / "video_generation"
COMFYUI_DIR = VIDEO_ROOT / "ComfyUI"
COMFYUI_ENV = VIDEO_ROOT / "runtime"
COMFYUI_MODELS = VIDEO_ROOT / "models"
COMFYUI_INPUT = VIDEO_ROOT / "input"
COMFYUI_OUTPUT = VIDEO_ROOT / "output"
COMFYUI_TEMP = VIDEO_ROOT / "temp"
COMFYUI_CUSTOM_NODES = VIDEO_ROOT / "custom_nodes"
COMFYUI_MARKER = VIDEO_ROOT / ".neve-runtime-ready"
VIDEO_HF_CACHE = VIDEO_ROOT / "huggingface"

DIFFUSION_MODEL = "minimax_h3_fl2va_pruned_w4a8_mixed.safetensors"
TEXT_ENCODER = "qwen3vl_4b_fp8_scaled.safetensors"
CLIP_PROJECTION = "mmh3-4b-ClipProj-v3.1.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
TURBO_LORA = "minimax_h3_turbo_v4_step600_ema.safetensors"

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 576
DEFAULT_FRAMES = 124
DEFAULT_STEPS = 8
DEFAULT_FPS = 24.0
VIDEO_DIMENSION_MULTIPLE = 32
GENERATION_TIMEOUT_SECONDS = 60 * 60
VIDEO_GPU_POWER_RATIO = 0.83
VIDEO_GPU_MAX_TEMPERATURE_C = 76.0
VIDEO_GPU_TEMPERATURE_POLL_SECONDS = 0.5


def _align_video_dimension(value: int) -> int:
    """Keep MiniMax H3 video and reference-image latents patch-compatible."""
    value = max(VIDEO_DIMENSION_MULTIPLE, int(value))
    return (
        (value + VIDEO_DIMENSION_MULTIPLE // 2) // VIDEO_DIMENSION_MULTIPLE
    ) * VIDEO_DIMENSION_MULTIPLE


def _hidden_process_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = getattr(asyncio.subprocess, "STARTUPINFO", None)
    if startupinfo is None:
        import subprocess

        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": info, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _is_amd_only_windows_system() -> bool:
    if os.name != "nt":
        return False
    try:
        import subprocess

        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Get-CimInstance Win32_VideoController | ForEach-Object Name",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        names = result.stdout.lower()
        has_amd = "amd" in names or "radeon" in names
        has_nvidia = "nvidia" in names or "geforce" in names
        return has_amd and not has_nvidia
    except Exception:
        return False


def _runtime_python() -> Path:
    if os.name == "nt":
        return COMFYUI_ENV / "Scripts" / "python.exe"
    return COMFYUI_ENV / "bin" / "python"


def _sageattention_wheel_url() -> str:
    if os.name != "nt":
        raise RuntimeError("O runtime MiniMax H3 otimizado atualmente requer Windows.")
    python_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    filename = (
        "sageattention-2.2.0%2Bcu130torch2.11-"
        f"{python_tag}-{python_tag}-win_amd64.whl"
    )
    return (
        "https://github.com/Comfy-Org/wheels/releases/download/"
        f"sageattention-latest/{filename}"
    )


def _replace_source_from_archive(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(VIDEO_ROOT)) as temporary:
        temporary_path = Path(temporary)
        archive_path = temporary_path / "source.zip"
        request = urllib.request.Request(url, headers={"User-Agent": "NeveAI/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            with archive_path.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temporary_path / "extracted")
        roots = [path for path in (temporary_path / "extracted").iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("O pacote do gerador de video possui uma estrutura inesperada.")
        replacement = destination.with_name(f"{destination.name}.new")
        if replacement.exists():
            shutil.rmtree(replacement)
        shutil.move(str(roots[0]), str(replacement))
        if destination.exists():
            shutil.rmtree(destination)
        replacement.replace(destination)


class MiniMaxH3Runtime:
    def __init__(self) -> None:
        self.session_lock = asyncio.Lock()
        self._runtime_lock = asyncio.Lock()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._active_command: Optional[asyncio.subprocess.Process] = None
        self._log_task: Optional[asyncio.Task] = None
        self._port: Optional[int] = None
        self._prompt_id: Optional[str] = None
        self._cancel_requested = False
        self._thermal_guard_task: Optional[asyncio.Task] = None
        self._thermal_error: Optional[str] = None
        self._original_power_limit: Optional[float] = None
        self._log_tail: deque[str] = deque(maxlen=160)

    @property
    def is_installed(self) -> bool:
        try:
            marker = COMFYUI_MARKER.read_text(encoding="utf-8").strip()
        except OSError:
            return False
        return (
            marker == VIDEO_RUNTIME_REVISION
            and _runtime_python().is_file()
            and (COMFYUI_DIR / "main.py").is_file()
            and (COMFYUI_CUSTOM_NODES / "ComfyUI-ClipProj" / "__init__.py").is_file()
            and (COMFYUI_CUSTOM_NODES / "ComfyUI-MiniMax-H3-Turbo" / "__init__.py").is_file()
        )

    @property
    def models_ready(self) -> bool:
        return all(path.is_file() and path.stat().st_size > 1024 for path in self._model_paths())

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @staticmethod
    def _model_paths() -> tuple[Path, ...]:
        return (
            COMFYUI_MODELS / "diffusion_models" / DIFFUSION_MODEL,
            COMFYUI_MODELS / "text_encoders" / TEXT_ENCODER,
            COMFYUI_MODELS / "clip_projections" / CLIP_PROJECTION,
            COMFYUI_MODELS / "vae" / VIDEO_VAE,
            COMFYUI_MODELS / "loras" / TURBO_LORA,
        )

    async def _run_command(self, command: list[str], cwd: Optional[Path] = None) -> None:
        self._active_command = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **_hidden_process_kwargs(),
        )
        output: deque[str] = deque(maxlen=80)
        try:
            if self._active_command.stdout is not None:
                while line := await self._active_command.stdout.readline():
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    output.append(decoded)
                    log.debug("MiniMax H3 setup: %s", decoded)
            return_code = await self._active_command.wait()
        except asyncio.CancelledError:
            await self._terminate_process(self._active_command)
            raise
        finally:
            self._active_command = None
        if return_code != 0:
            details = "\n".join(output)
            raise RuntimeError(
                "Nao foi possivel preparar o ambiente de video."
                + (f"\n{details}" if details else "")
            )

    async def _ensure_uv(self) -> None:
        check = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "uv",
            "--version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            **_hidden_process_kwargs(),
        )
        if await check.wait() == 0:
            return
        await self._run_command([sys.executable, "-m", "pip", "install", "uv>=0.8,<1"])

    async def ensure_installed(self, progress: ProgressCallback) -> None:
        if self.is_installed:
            return
        async with self._runtime_lock:
            if self.is_installed:
                return
            if await asyncio.to_thread(_is_amd_only_windows_system):
                raise RuntimeError(
                    "O Criar video com MiniMax H3 requer NVIDIA CUDA; este pipeline "
                    "nao possui backend Vulkan compativel para GPUs AMD."
                )
            if sys.version_info[:2] not in {(3, 11), (3, 12), (3, 13)}:
                raise RuntimeError("A geracao de video requer Python 3.11, 3.12 ou 3.13.")

            VIDEO_ROOT.mkdir(parents=True, exist_ok=True)
            await progress("Preparando o gerador de video...")
            await self._ensure_uv()
            await asyncio.to_thread(
                _replace_source_from_archive,
                f"https://github.com/Comfy-Org/ComfyUI/archive/{COMFYUI_COMMIT}.zip",
                COMFYUI_DIR,
            )
            await asyncio.to_thread(
                _replace_source_from_archive,
                f"https://github.com/nicolab28/ComfyUI-ClipProj/archive/{CLIPPROJ_COMMIT}.zip",
                COMFYUI_CUSTOM_NODES / "ComfyUI-ClipProj",
            )
            await asyncio.to_thread(
                _replace_source_from_archive,
                f"https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo/archive/{TURBO_NODE_COMMIT}.zip",
                COMFYUI_CUSTOM_NODES / "ComfyUI-MiniMax-H3-Turbo",
            )

            await progress("Instalando o ambiente isolado de video...")
            await self._run_command(
                [
                    sys.executable,
                    "-m",
                    "uv",
                    "venv",
                    str(COMFYUI_ENV),
                    "--python",
                    sys.executable,
                    "--clear",
                ]
            )
            runtime_python = str(_runtime_python())
            await self._run_command(
                [
                    sys.executable,
                    "-m",
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    runtime_python,
                    "torch==2.11.0",
                    "torchvision",
                    "torchaudio",
                    "--index-url",
                    "https://download.pytorch.org/whl/cu130",
                ]
            )
            await self._run_command(
                [
                    sys.executable,
                    "-m",
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    runtime_python,
                    "-r",
                    str(COMFYUI_DIR / "requirements.txt"),
                    "huggingface_hub>=0.34,<2",
                ]
            )
            await self._run_command(
                [
                    sys.executable,
                    "-m",
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    runtime_python,
                    "triton-windows>=3.6,<3.7",
                    _sageattention_wheel_url(),
                ]
            )
            await self._run_command(
                [
                    runtime_python,
                    "-c",
                    "import torch, sageattention; "
                    "assert torch.cuda.is_available(), 'CUDA indisponivel'; "
                    "assert torch.cuda.get_device_capability()[0] >= 12, 'GPU Blackwell necessaria'",
                ]
            )
            COMFYUI_MARKER.write_text(VIDEO_RUNTIME_REVISION, encoding="utf-8")

    @staticmethod
    def _directory_size(directory: Path) -> int:
        total = 0
        if not directory.exists():
            return total
        for root, _, files in os.walk(directory):
            for filename in files:
                try:
                    total += (Path(root) / filename).stat().st_size
                except OSError:
                    pass
        return total

    @staticmethod
    def _format_size(size: int) -> str:
        return f"{size / 1024**3:.1f} GB" if size >= 1024**3 else f"{size / 1024**2:.0f} MB"

    async def ensure_models(self, progress: ProgressCallback) -> None:
        if self.models_ready:
            return
        for directory in (
            COMFYUI_MODELS / "diffusion_models",
            COMFYUI_MODELS / "text_encoders",
            COMFYUI_MODELS / "clip_projections",
            COMFYUI_MODELS / "vae",
            COMFYUI_MODELS / "loras",
            VIDEO_HF_CACHE,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        await progress("Baixando os modelos de video...")
        script = f"""
from huggingface_hub import hf_hub_download
items = {[
    ('Kijai/MiniMax-H3-experimental', DIFFUSION_MODEL, str(COMFYUI_MODELS / 'diffusion_models')),
    ('Comfy-Org/Krea-2', f'text_encoders/{TEXT_ENCODER}', str(COMFYUI_MODELS)),
    ('NicoLab28/ClipProj-MiniMax-H3', CLIP_PROJECTION, str(COMFYUI_MODELS / 'clip_projections')),
    ('Comfy-Org/MiniMax-H3', f'vae/{VIDEO_VAE}', str(COMFYUI_MODELS)),
    ('larryvrh/MiniMax-H3-Turbo-Lora', TURBO_LORA, str(COMFYUI_MODELS / 'loras')),
]!r}
for repo_id, filename, local_dir in items:
    hf_hub_download(repo_id=repo_id, filename=filename, local_dir=local_dir)
"""
        initial_size = await asyncio.to_thread(self._directory_size, COMFYUI_MODELS)
        task = asyncio.create_task(self._run_command([str(_runtime_python()), "-c", script]))
        last_reported = -1
        try:
            while not task.done():
                await asyncio.sleep(2)
                current = await asyncio.to_thread(self._directory_size, COMFYUI_MODELS)
                downloaded = max(0, current - initial_size)
                rounded = downloaded // (256 * 1024 * 1024)
                if rounded != last_reported:
                    last_reported = rounded
                    await progress(f"Baixando os modelos de video... {self._format_size(downloaded)}")
            await task
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if not self.models_ready:
            raise RuntimeError("O download dos modelos de video nao foi concluido.")

    async def prepare(self, progress: ProgressCallback) -> None:
        await self.ensure_installed(progress)
        await self.ensure_models(progress)

    @staticmethod
    def _available_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    @staticmethod
    async def _nvidia_smi(*arguments: str) -> Optional[str]:
        executable = shutil.which("nvidia-smi")
        if not executable:
            return None
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                **_hidden_process_kwargs(),
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5)
            if process.returncode != 0:
                return None
            return stdout.decode("utf-8", errors="replace").strip()
        except (OSError, asyncio.TimeoutError):
            return None

    async def _apply_safe_power_limit(self) -> None:
        output = await self._nvidia_smi(
            "--query-gpu=power.limit,power.default_limit,power.min_limit",
            "--format=csv,noheader,nounits",
        )
        if not output:
            log.warning("Video thermal guard: nvidia-smi power data unavailable.")
            return
        try:
            current, default, minimum = (
                float(value.strip()) for value in output.splitlines()[0].split(",")
            )
        except (ValueError, IndexError):
            log.warning("Video thermal guard: invalid nvidia-smi power data: %s", output)
            return

        target = max(minimum, min(current, default * VIDEO_GPU_POWER_RATIO))
        if target >= current - 0.5:
            return
        changed = await self._nvidia_smi("--power-limit", f"{target:.0f}")
        if changed is None:
            log.warning("Video thermal guard: could not apply the temporary power limit.")
            return
        self._original_power_limit = current
        log.info(
            "Video thermal guard: temporary GPU power limit %.0f W (was %.0f W).",
            target,
            current,
        )

    async def _restore_power_limit(self) -> None:
        original = self._original_power_limit
        self._original_power_limit = None
        if original is None:
            return
        if await self._nvidia_smi("--power-limit", f"{original:.0f}") is None:
            log.warning("Video thermal guard: could not restore GPU power limit %.0f W.", original)
        else:
            log.info("Video thermal guard: restored GPU power limit %.0f W.", original)

    async def _thermal_guard(self) -> None:
        while self._process is not None and self._process.returncode is None:
            output = await self._nvidia_smi(
                "--query-gpu=temperature.gpu",
                "--format=csv,noheader,nounits",
            )
            try:
                temperature = float(output.splitlines()[0]) if output else None
            except (ValueError, IndexError):
                temperature = None
            if temperature is not None and temperature >= VIDEO_GPU_MAX_TEMPERATURE_C:
                self._thermal_error = (
                    f"Geração interrompida para proteger a GPU: temperatura atingiu "
                    f"{temperature:.0f} °C."
                )
                log.warning(self._thermal_error)
                process = self._process
                if process is not None:
                    await self._terminate_process(process)
                return
            await asyncio.sleep(VIDEO_GPU_TEMPERATURE_POLL_SECONDS)

    async def _capture_output(self, process: asyncio.subprocess.Process) -> None:
        if process.stdout is None:
            return
        while line := await process.stdout.readline():
            decoded = line.decode("utf-8", errors="replace").rstrip()
            self._log_tail.append(decoded)
            log.debug("MiniMax H3: %s", decoded)

    async def _start_server(self, progress: ProgressCallback) -> str:
        await self.stop()
        self._cancel_requested = False
        self._thermal_error = None
        self._log_tail.clear()
        self._port = self._available_port()
        for directory in (COMFYUI_INPUT, COMFYUI_OUTPUT, COMFYUI_TEMP, VIDEO_HF_CACHE):
            directory.mkdir(parents=True, exist_ok=True)

        await progress("Iniciando a criação de video...", 3)
        await self._apply_safe_power_limit()
        env = os.environ.copy()
        env.update(
            {
                "PYTHONIOENCODING": "utf-8",
                "HF_HOME": str(VIDEO_HF_CACHE),
                "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            }
        )
        self._process = await asyncio.create_subprocess_exec(
            str(_runtime_python()),
            str(COMFYUI_DIR / "main.py"),
            "--listen",
            "127.0.0.1",
            "--port",
            str(self._port),
            "--base-directory",
            str(VIDEO_ROOT),
            "--output-directory",
            str(COMFYUI_OUTPUT),
            "--temp-directory",
            str(COMFYUI_TEMP),
            "--input-directory",
            str(COMFYUI_INPUT),
            "--disable-auto-launch",
            "--preview-method",
            "none",
            "--cache-none",
            "--enable-dynamic-vram",
            "--reserve-vram",
            "0.75",
            "--use-sage-attention",
            "--disable-metadata",
            cwd=str(COMFYUI_DIR),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **_hidden_process_kwargs(),
        )
        process = self._process
        self._log_task = asyncio.create_task(self._capture_output(process))
        self._thermal_guard_task = asyncio.create_task(self._thermal_guard())
        base_url = f"http://127.0.0.1:{self._port}"
        startup_progress = 3
        async with httpx.AsyncClient(timeout=2.0) as client:
            for attempt in range(600):
                if self._cancel_requested:
                    raise asyncio.CancelledError
                if process.returncode is not None:
                    if self._thermal_error:
                        raise RuntimeError(self._thermal_error)
                    details = "\n".join(self._log_tail)
                    raise RuntimeError(
                        "O gerador de video encerrou durante a inicializacao."
                        + (f"\n{details[-3000:]}" if details else "")
                    )
                try:
                    response = await client.get(f"{base_url}/system_stats")
                    if response.is_success:
                        await progress("Iniciando a criação de video...", 14)
                        return base_url
                except httpx.HTTPError:
                    pass
                if attempt and attempt % 4 == 0 and startup_progress < 13:
                    startup_progress += 1
                    await progress("Iniciando a criação de video...", startup_progress)
                await asyncio.sleep(0.5)
        raise RuntimeError("O gerador de video nao respondeu dentro do tempo esperado.")

    @staticmethod
    def _build_workflow(
        prompt: str,
        seed: int,
        input_image: Optional[str],
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        frames: int = DEFAULT_FRAMES,
    ) -> dict:
        width = _align_video_dimension(width)
        height = _align_video_dimension(height)
        workflow: dict[str, dict] = {
            "1": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": TEXT_ENCODER, "type": "krea2", "device": "default"},
            },
            "2": {
                "class_type": "ClipProjApply",
                "inputs": {"clip": ["1", 0], "projection": CLIP_PROJECTION},
            },
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_VAE}},
            "4": {
                "class_type": "MiniMaxH3ImageToVideo",
                "inputs": {
                    "clip": ["2", 0],
                    "vae": ["3", 0],
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "length": frames,
                },
            },
            "5": {
                "class_type": "ClipProjFree",
                "inputs": {"scope": "all models", "after": ["4", 0]},
            },
            "6": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": DIFFUSION_MODEL, "weight_dtype": "default"},
            },
            "7": {
                "class_type": "MiniMaxH3TurboLoRA",
                "inputs": {
                    "model": ["6", 0],
                    "lora_name": TURBO_LORA,
                    "strength": 1.0,
                    "low_vram": True,
                },
            },
            "8": {
                "class_type": "BasicGuider",
                "inputs": {"model": ["7", 0], "conditioning": ["5", 0]},
            },
            "9": {
                "class_type": "BasicScheduler",
                "inputs": {"model": ["7", 0], "scheduler": "simple", "steps": DEFAULT_STEPS, "denoise": 1.0},
            },
            "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "11": {"class_type": "MiniMaxH3TurboSampler", "inputs": {}},
            "12": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["10", 0],
                    "guider": ["8", 0],
                    "sampler": ["11", 0],
                    "sigmas": ["9", 0],
                    "latent_image": ["4", 1],
                },
            },
            "13": {
                "class_type": "ClipProjFree",
                "inputs": {"scope": "all models", "after": ["12", 0]},
            },
            "14": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["13", 0], "vae": ["3", 0]},
            },
            "15": {
                "class_type": "CreateVideo",
                "inputs": {"images": ["14", 0], "fps": DEFAULT_FPS},
            },
            "16": {
                "class_type": "SaveVideo",
                "inputs": {
                    "video": ["15", 0],
                    "filename_prefix": "video/NeveAI_MiniMax_H3",
                    "format": "auto",
                    "codec": "auto",
                },
            },
        }
        if input_image:
            workflow["20"] = {
                "class_type": "LoadImage",
                "inputs": {"image": input_image},
            }
            workflow["4"]["inputs"]["first_frame"] = ["20", 0]
        return workflow

    async def _upload_image(self, client: httpx.AsyncClient, image: tuple[str, bytes, str]) -> str:
        name, content, content_type = image
        response = await client.post(
            "/upload/image",
            files={"image": (name, content, content_type)},
            data={"type": "input", "overwrite": "true"},
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("name") or name)

    @staticmethod
    def _find_output_file(history: dict) -> Optional[dict]:
        outputs = history.get("outputs") if isinstance(history, dict) else None
        if not isinstance(outputs, dict):
            return None
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for value in node_output.values():
                if not isinstance(value, list):
                    continue
                for item in value:
                    if not isinstance(item, dict) or not item.get("filename"):
                        continue
                    filename = str(item["filename"])
                    if filename.lower().endswith((".mp4", ".webm", ".mov", ".mkv")):
                        return item
        return None

    async def generate(
        self,
        prompt: str,
        progress: ProgressCallback,
        image: Optional[tuple[str, bytes, str]] = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        frames: int = DEFAULT_FRAMES,
    ) -> dict:
        prompt = str(prompt or "").strip()
        if not prompt:
            raise ValueError("Descreva o video que deseja criar.")
        base_url = await self._start_server(progress)
        timeout = httpx.Timeout(connect=20, read=120, write=120, pool=20)
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            input_image = None
            if image is not None:
                await progress("Preparando a imagem de referencia...")
                input_image = await self._upload_image(client, image)

            await progress("Gerando o conditioning...", 15)
            workflow = self._build_workflow(
                prompt,
                random.randint(0, 2**63 - 1),
                input_image,
                width=width,
                height=height,
                frames=frames,
            )
            client_id = f"neveai-{random.randint(1, 2**31)}"
            websocket = None
            websocket_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None))
            try:
                websocket_url = base_url.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
                try:
                    websocket = await websocket_session.ws_connect(
                        f"{websocket_url}/ws?clientId={urllib.parse.quote(client_id)}",
                        heartbeat=30,
                    )
                except Exception as exc:
                    log.warning("ComfyUI progress websocket unavailable: %s", exc)

                response = await client.post(
                    "/prompt",
                    json={"prompt": workflow, "client_id": client_id},
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("node_errors"):
                    raise RuntimeError(
                        f"Workflow invalido: {json.dumps(payload['node_errors'], ensure_ascii=False)}"
                    )
                self._prompt_id = str(payload.get("prompt_id") or "")
                if not self._prompt_id:
                    raise RuntimeError("O ComfyUI nao retornou um identificador de tarefa.")

                started = asyncio.get_running_loop().time()
                best_progress = 18
                current_node = ""
                last_progress_at = asyncio.get_running_loop().time()
                next_history_check = 0.0
                await progress("Criando o vídeo...", best_progress)
                node_progress_bounds = {
                    "1": (18, 20),
                    "2": (20, 22),
                    "3": (22, 24),
                    "4": (24, 29),
                    "5": (29, 31),
                    "6": (31, 34),
                    "7": (34, 36),
                    "8": (36, 38),
                    "9": (38, 39),
                    "10": (39, 40),
                    "11": (40, 42),
                    "12": (42, 89),
                    "13": (89, 91),
                    "14": (91, 97),
                    "15": (97, 98),
                    "16": (98, 99),
                }
                while asyncio.get_running_loop().time() - started < GENERATION_TIMEOUT_SECONDS:
                    if self._cancel_requested:
                        raise asyncio.CancelledError
                    if self._process is None or self._process.returncode is not None:
                        if self._thermal_error:
                            raise RuntimeError(self._thermal_error)
                        details = "\n".join(self._log_tail)
                        raise RuntimeError(
                            "O gerador de video encerrou durante a tarefa."
                            + (f" {details[-2500:]}" if details else "")
                        )

                    if websocket is not None and not websocket.closed:
                        try:
                            message = await websocket.receive(timeout=0.75)
                            if message.type == aiohttp.WSMsgType.TEXT:
                                event = json.loads(message.data)
                                event_data = event.get("data") or {}
                                event_prompt_id = str(event_data.get("prompt_id") or "")
                                event_type = str(event.get("type") or "")
                                if event_type == "executing" and (
                                    not event_prompt_id or event_prompt_id == self._prompt_id
                                ):
                                    current_node = str(event_data.get("node") or "")
                                    bounds = node_progress_bounds.get(current_node)
                                    if bounds and bounds[0] > best_progress:
                                        best_progress = bounds[0]
                                        last_progress_at = asyncio.get_running_loop().time()
                                        await progress("Criando o vídeo...", best_progress)
                                if event_type == "progress" and (
                                    not event_prompt_id or event_prompt_id == self._prompt_id
                                ):
                                    value = int(event_data.get("value") or 0)
                                    maximum = int(event_data.get("max") or 0)
                                    progress_node = str(event_data.get("node") or current_node)
                                    bounds = node_progress_bounds.get(progress_node, (best_progress, 98))
                                    if maximum > 0:
                                        measured = min(
                                            bounds[1],
                                            max(
                                                bounds[0],
                                                bounds[0]
                                                + round(
                                                    (value / maximum)
                                                    * (bounds[1] - bounds[0])
                                                ),
                                            ),
                                        )
                                        if measured > best_progress:
                                            best_progress = measured
                                            last_progress_at = asyncio.get_running_loop().time()
                                            await progress(
                                                "Criando o vídeo...",
                                                best_progress,
                                            )
                        except asyncio.TimeoutError:
                            pass
                        except Exception as exc:
                            log.debug("ComfyUI progress event ignored: %s", exc)
                            websocket = None
                    else:
                        await asyncio.sleep(0.25)

                    now = asyncio.get_running_loop().time()
                    if now - last_progress_at >= 1.0 and best_progress < 99:
                        phase_ceiling = node_progress_bounds.get(
                            current_node, (best_progress, 41)
                        )[1]
                        if best_progress < phase_ceiling:
                            best_progress += 1
                            last_progress_at = now
                            await progress("Criando o vídeo...", best_progress)
                    if now < next_history_check:
                        continue
                    next_history_check = now + 2
                    history_response = await client.get(f"/history/{self._prompt_id}")
                    history_response.raise_for_status()
                    history_payload = history_response.json()
                    history = history_payload.get(self._prompt_id)
                    if isinstance(history, dict):
                        status = history.get("status") or {}
                        if status.get("status_str") == "error" or status.get("completed") is False:
                            messages = status.get("messages") or []
                            raise RuntimeError(f"O workflow de video falhou: {messages[-1] if messages else 'erro desconhecido'}")
                        output = self._find_output_file(history)
                        if output:
                            params = {
                                "filename": output["filename"],
                                "subfolder": output.get("subfolder", ""),
                                "type": output.get("type", "output"),
                            }
                            file_response = await client.get("/view", params=params, timeout=None)
                            file_response.raise_for_status()
                            content_type = file_response.headers.get("content-type", "video/mp4").split(";", 1)[0]
                            await progress("Criando o vídeo...", 100)
                            return {
                                "video": file_response.content,
                                "content_type": content_type,
                                "filename": Path(str(output["filename"])).name,
                            }
            finally:
                if websocket is not None and not websocket.closed:
                    await websocket.close()
                await websocket_session.close()
        raise RuntimeError("A geracao de video excedeu o tempo limite.")

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

    async def stop(self) -> None:
        process = self._process
        self._process = None
        self._port = None
        self._prompt_id = None
        thermal_guard_task = self._thermal_guard_task
        self._thermal_guard_task = None
        if thermal_guard_task is not None and thermal_guard_task is not asyncio.current_task():
            if not thermal_guard_task.done():
                thermal_guard_task.cancel()
            try:
                await thermal_guard_task
            except asyncio.CancelledError:
                pass
        if process is not None:
            await self._terminate_process(process)
        if self._log_task is not None:
            try:
                await asyncio.wait_for(self._log_task, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._log_task.cancel()
            self._log_task = None
        await self._restore_power_limit()

    async def cancel(self) -> None:
        self._cancel_requested = True
        process = self._active_command
        if process is not None:
            await self._terminate_process(process)
        if self._process is not None and self._port is not None:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    await client.post(f"http://127.0.0.1:{self._port}/interrupt")
                    if self._prompt_id:
                        await client.post(
                            f"http://127.0.0.1:{self._port}/queue",
                            json={"delete": [self._prompt_id]},
                        )
            except httpx.HTTPError:
                pass
        await self.stop()


minimax_h3_runtime = MiniMaxH3Runtime()


@router.get("/status")
async def get_video_generation_status(request: Request, user=Depends(get_verified_user)):
    return {
        "enabled": request.app.state.config.ENABLE_VIDEO_GENERATION,
        "installed": minimax_h3_runtime.is_installed,
        "models_ready": minimax_h3_runtime.models_ready,
        "running": minimax_h3_runtime.is_running,
        "model": "MiniMax H3 FL2VA W4A8",
    }


@router.post("/cancel")
async def cancel_video_generation(request: Request, user=Depends(get_verified_user)):
    if not has_permission(
        user.id,
        "features.video_generation",
        request.app.state.config.USER_PERMISSIONS,
    ):
        raise HTTPException(status_code=403, detail=ERROR_MESSAGES.ACCESS_PROHIBITED)
    await minimax_h3_runtime.cancel()
    return {"success": True}
