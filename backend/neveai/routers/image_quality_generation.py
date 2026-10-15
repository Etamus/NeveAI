"""ComfyUI image generation with a separate PE-I2I planning stage."""

import asyncio
import base64
import csv
import io
import json
import logging
import math
import os
import random
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Awaitable, Callable, Optional

import aiohttp
import httpx
import psutil
from huggingface_hub import hf_hub_download
from PIL import Image, ImageOps

from neveai.config import CACHE_DIR
from neveai.utils.image_memory import cpu_image_requested, cpu_image_size, is_image_memory_error, monotonic_progress, worker_error
from neveai.routers import image_fast_generation as fast
from neveai.routers.stable_diffusion import (
    QWEN_IMAGE_21_REPO,
    QWEN_IMAGE_21_OFFICIAL_STEPS,
    _detected_gpu_vram_mib,
    _normalize_qwen_reference_tokens,
    _read_image_reference_bytes,
    qwen_image_dimensions,
)

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int], Awaitable[None]]
DimensionsCallback = Callable[[int, int], Awaitable[None]]

ROOT = CACHE_DIR / "image_quality_generation"
PE_DIR = ROOT / "pe"
MODEL_REPO = QWEN_IMAGE_21_REPO
MODEL_FILE = "qwen-image-2.1-UC-Q6_K.gguf"
EDIT_MODEL_FILE = "qwen-image-2.1-UC-int8_convrot.safetensors"
EDIT_MODEL_REPO = "abenzerps/Qwen-Image-2.1-Uncensored-Quantized"
EDIT_MODEL_REVISION = "7959e658915f52274897fb573ffeda49de8dc16b"
EDIT_MODEL_BYTES = 7256796840
ENCODER_REPO = "Comfy-Org/Qwen-Image-2.1"
ENCODER_FILE = "qwen3vl_8b_int8_convrot.safetensors"
VAE_FILE = "qwen_image_2.1_vae_bf16.safetensors"
PE_REPO = "pottokao/Qwen-Image-2.1-PE-I2I-Heretic-GGUF"
PE_FILE = "pe_i2i_heretic-Q6_K.gguf"
PE_LOW_VRAM_FILE = "pe_i2i_heretic-Q4_K_M.gguf"
PE_VISION_FILE = "pe_i2i_heretic.mmproj-bf16.gguf"
PE_SYSTEM_REPO = PE_REPO
PE_SYSTEM_FILE = "system_prompt.txt"
PE_THINKING_TOKENS = 600
STEPS = QWEN_IMAGE_21_OFFICIAL_STEPS
REFERENCE_PIXELS = 1152 * 1152
MAX_REFERENCE_SIDE = 1536
EDIT_REFERENCE_PIXELS = 2048 * 1024
EDIT_MAX_REFERENCE_SIDE = 2048
PE_Q6_MIN_VRAM_MIB = 12 * 1024
CFG1_NODE_FILE = "neve_image_quality_cfg1.py"
BALANCED_EDIT_REFERENCES = 4
MAX_INT8_EDIT_REFERENCES = 10
BALANCED_EDIT_PIXELS = 3 * 1024 * 1024
BALANCED_CANVAS_AREA_GAIN = 1.6
BALANCED_AUXILIARY_PIXELS = 1024 * 1024
BALANCED_MAX_SIDE = 2560
BALANCED_MIN_RAM = 24 * 1024 * 1024 * 1024


def _install_cfg1_node() -> None:
    source = Path(__file__).resolve().parents[1] / "utils" / "image_quality_cfg1_node.py"
    target = fast.CUSTOM_NODES_DIR / CFG1_NODE_FILE
    content = source.read_bytes()
    if target.is_file() and target.read_bytes() == content:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _pe_file_for_hardware() -> str:
    vram_mib = _detected_gpu_vram_mib()
    return PE_FILE if vram_mib is not None and vram_mib >= PE_Q6_MIN_VRAM_MIB else PE_LOW_VRAM_FILE


def _prefer_int8_edit(reference_count: int) -> bool:
    # Keep the bounded editing profile off smaller/unknown GPUs and other backends.
    if not 1 <= reference_count <= MAX_INT8_EDIT_REFERENCES or os.name != "nt" or not shutil.which("nvidia-smi"):
        return False
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in (None, "0"):
        return False
    try:
        if reference_count >= BALANCED_EDIT_REFERENCES and psutil.virtual_memory().total < BALANCED_MIN_RAM:
            return False
        result = subprocess.run(
            ["nvidia-smi", "--id=0", "--query-gpu=memory.total,compute_cap", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=False,
            **fast._process_kwargs(),
        )
        if result.returncode:
            return False
        memory, capability = next(csv.reader(io.StringIO(result.stdout)))
        return int(memory.strip()) >= 15 * 1024 and float(capability.strip()) >= 8.0
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
        return False


def _fit_reference(width: int, height: int, *, detailed_edit: bool = False) -> tuple[int, int]:
    if width < 1 or height < 1:
        raise ValueError("Imagem de referencia invalida")
    if detailed_edit and width * height > REFERENCE_PIXELS:
        # Preserve source detail instead of shrinking every edit to the old 1.3 MP canvas.
        scale = min(1.0, math.sqrt(EDIT_REFERENCE_PIXELS / (width * height)), EDIT_MAX_REFERENCE_SIDE / max(width, height))
    else:
        scale = min(math.sqrt(REFERENCE_PIXELS / (width * height)), MAX_REFERENCE_SIDE / max(width, height))
    return (
        max(256, round(width * scale / 32) * 32),
        max(256, round(height * scale / 32) * 32),
    )


def _fit_balanced_reference(width: int, height: int, index: int, count: int = BALANCED_EDIT_REFERENCES) -> tuple[int, int]:
    if (width < 1 or height < 1 or not BALANCED_EDIT_REFERENCES <= count <= MAX_INT8_EDIT_REFERENCES
            or not 0 <= index < count):
        raise ValueError("Imagem de referencia invalida")
    if index == 0:
        budget = min(BALANCED_EDIT_PIXELS, max(REFERENCE_PIXELS, width * height * BALANCED_CANVAS_AREA_GAIN))
    else:
        # Tiny identity/style references do not need full canvas-sized upscaling.
        budget = BALANCED_AUXILIARY_PIXELS / (count - 1)
    scale = min(math.sqrt(budget / (width * height)), BALANCED_MAX_SIDE / max(width, height))
    return tuple(max(32, round(side * scale / 32) * 32) for side in (width, height))


def _extract_pe_prompt(content: str) -> str:
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("rewritten_prompt"), str):
            prompt = value["rewritten_prompt"].strip()
            if prompt:
                return prompt
    raise RuntimeError("PE-I2I nao retornou um prompt de edicao valido.")


class NeveImage21Runtime:
    NAME = "Neve Image 2.4"
    PE_CONTEXT = 16384
    PE_REASONING_BUDGET = PE_THINKING_TOKENS
    PE_RESPONSE_TOKENS = 1800

    def __init__(self) -> None:
        self._lock = fast.neve_image_2s_runtime._lock
        self._request_lock = asyncio.Lock()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._log_task: Optional[asyncio.Task] = None
        self._log_tail: list[str] = []
        self._port: Optional[int] = None
        self._cfg1_node_ready = False
        self._force_gguf = False
        self._cpu_mode = False
        self._memory_saver = False
        self._retry_prompt = None

    @staticmethod
    def build_workflow(prompt: str, width: int, height: int, refs: list[str], seed: int, model_file: str = MODEL_FILE) -> dict:
        if len(refs) > 10:
            raise ValueError("Neve Image 2.4 aceita ate dez imagens de referencia.")
        if refs:
            prompt = _normalize_qwen_reference_tokens(prompt, len(refs))
        workflow = {
            "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": MODEL_FILE}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": ENCODER_FILE, "type": "qwen_image", "device": "default"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_FILE}},
            "4": {"class_type": "TextEncodeQwenImage21", "inputs": {
                "clip": ["2", 0], "vae": ["3", 0], "prompt": prompt,
                "negative_prompt": "", "resolution": 0 if refs else 1024,
            }},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1],
                "latent_image": ["4", 2] if refs else ["6", 0],
                "seed": seed, "steps": STEPS, "cfg": 1.0,
                "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
            }},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["3", 0]}},
            "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "neve_image_21"}},
        }
        if model_file == EDIT_MODEL_FILE:
            workflow["1"] = {"class_type": "UNETLoader", "inputs": {"unet_name": model_file, "weight_dtype": "default"}}
            if refs:
                workflow["4"]["class_type"] = "NeveTextEncodeQwenImage21CFG1"
            if BALANCED_EDIT_REFERENCES <= len(refs) <= MAX_INT8_EDIT_REFERENCES:
                workflow["30"] = {"class_type": "QwenImage21Cache", "inputs": {
                    "model": ["1", 0], "device": "cpu", "dtype": "default",
                }}
                workflow["5"]["inputs"]["model"] = ["30", 0]
        if not refs:
            workflow["6"] = {"class_type": "EmptyLatentImage", "inputs": {
                "width": width, "height": height, "batch_size": 1,
            }}
        for index, filename in enumerate(refs, 1):
            node = str(8 + index)
            workflow[node] = {"class_type": "LoadImage", "inputs": {"image": filename}}
            workflow["4"]["inputs"][f"images.image_{index}"] = [node, 0]
        return workflow

    async def _ensure_models(self, progress: ProgressCallback, edit: bool, reference_count: int = 0) -> str:
        await fast.neve_image_2s_runtime._install(progress, cpu_mode=self._cpu_mode)
        models = fast.MODELS_DIR
        model_file = MODEL_FILE
        if edit and not self._force_gguf and await asyncio.to_thread(_prefer_int8_edit, reference_count):
            target = models / "diffusion_models" / EDIT_MODEL_FILE
            try:
                if not target.is_file() or target.stat().st_size != EDIT_MODEL_BYTES:
                    await asyncio.to_thread(
                        hf_hub_download, repo_id=EDIT_MODEL_REPO, filename=EDIT_MODEL_FILE,
                        revision=EDIT_MODEL_REVISION, local_dir=str(target.parent),
                    )
                if target.is_file() and target.stat().st_size == EDIT_MODEL_BYTES:
                    model_file = EDIT_MODEL_FILE
                else:
                    raise RuntimeError("Arquivo INT8 de edicao incompleto.")
            except (OSError, RuntimeError, httpx.HTTPError) as exc:
                log.warning("Neve Image 2.4: usando GGUF de edicao apos falha no INT8: %s", exc)
        diffusion = models / "diffusion_models" / model_file
        if not diffusion.is_file() or diffusion.stat().st_size < 1024:
            cached = await asyncio.to_thread(
                hf_hub_download, repo_id=MODEL_REPO, filename=MODEL_FILE,
                cache_dir=str(CACHE_DIR / "stable_diffusion" / "gguf"),
            )
            diffusion.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(Path(cached).resolve(), diffusion)
            except OSError:
                shutil.copy2(cached, diffusion)
        for filename, subdir in ((ENCODER_FILE, "text_encoders"), (VAE_FILE, "vae")):
            target = models / subdir / filename
            if not target.is_file() or target.stat().st_size < 1024:
                await asyncio.to_thread(
                    hf_hub_download, repo_id=ENCODER_REPO,
                    filename=f"{subdir}/{filename}", local_dir=str(models),
                )
        self._cfg1_node_ready = False
        if model_file == EDIT_MODEL_FILE:
            try:
                await asyncio.to_thread(_install_cfg1_node)
                self._cfg1_node_ready = True
            except OSError as exc:
                log.warning("Neve Image 2.4: usando condicionador original apos falha no adaptador CFG1: %s", exc)
        if edit:
            PE_DIR.mkdir(parents=True, exist_ok=True)
            pe_file = self._pe_file()
            for repo, filename in (
                (PE_REPO, pe_file), (PE_REPO, PE_VISION_FILE),
                (PE_SYSTEM_REPO, PE_SYSTEM_FILE),
            ):
                target = PE_DIR / filename
                if not target.is_file() or target.stat().st_size < 1024:
                    await asyncio.to_thread(hf_hub_download, repo_id=repo, filename=filename, local_dir=str(PE_DIR))
        await progress(18)
        return model_file

    async def _capture_logs(self, process: asyncio.subprocess.Process) -> None:
        while line := await process.stdout.readline():
            decoded = line.decode("utf-8", errors="replace").rstrip()
            self._log_tail.append(decoded)
            if len(self._log_tail) > 100:
                self._log_tail.pop(0)
            log.debug("%s worker: %s", self.NAME, decoded)

    async def _stop(self) -> None:
        process, self._process = self._process, None
        self._port = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        if self._log_task is not None:
            try:
                await asyncio.wait_for(self._log_task, 2)
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

    async def _start(self, command: list[str], cwd: Path) -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = int(listener.getsockname()[1])
        self._port = port
        self._log_tail.clear()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        self._process = await asyncio.create_subprocess_exec(
            *command, "--port", str(port), cwd=str(cwd), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            **fast._process_kwargs(),
        )
        self._log_task = asyncio.create_task(self._capture_logs(self._process))
        base = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient(timeout=2) as client:
            for _ in range(240):
                if self._process.returncode is not None:
                    raise RuntimeError(f"{self.NAME} worker encerrou:\n" + "\n".join(self._log_tail[-25:]))
                try:
                    response = await client.get(f"{base}/health" if "llama-server" in command[0] else f"{base}/system_stats")
                    if response.is_success:
                        return base
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
        raise RuntimeError(f"{self.NAME} worker nao respondeu: " + "\n".join(self._log_tail[-10:]))

    def _pe_file(self) -> str:
        return PE_LOW_VRAM_FILE if self._cpu_mode else _pe_file_for_hardware()

    def _pe_directory(self) -> Path:
        return PE_DIR

    async def _plan_edit(self, prompt: str, images: list[bytes], progress: ProgressCallback) -> str:
        from neveai.routers.llamacpp import LLAMACPP_SERVER_BIN

        if not LLAMACPP_SERVER_BIN.is_file():
            raise RuntimeError("llama-server nao instalado para o PE-I2I.")
        pe_file = self._pe_file()
        pe_dir = self._pe_directory()
        command = [
            str(LLAMACPP_SERVER_BIN), "--host", "127.0.0.1", "--model", str(pe_dir / pe_file),
            "--mmproj", str(pe_dir / PE_VISION_FILE), "--ctx-size", str(self.PE_CONTEXT),
            "--parallel", "1", "--n-gpu-layers", "0" if self._cpu_mode else "99", "--reasoning", "on",
            "--reasoning-budget", str(self.PE_REASONING_BUDGET), "--no-webui",
            *(["--no-mmproj-offload"] if self._cpu_mode else []),
        ]
        try:
            base = await self._start(command, LLAMACPP_SERVER_BIN.parent)
            await progress(22)
            system = (pe_dir / PE_SYSTEM_FILE).read_text(encoding="utf-8").strip()
            content = [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(raw).decode("ascii")}}
                for raw in images
            ]
            content.append({"type": "text", "text": _normalize_qwen_reference_tokens(prompt, len(images))})
            request = {
                "model": pe_file,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.7, "max_tokens": self.PE_RESPONSE_TOKENS, "stream": False,
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=1800 if self._cpu_mode else 300, write=120, pool=30)) as client:
                response = await client.post(f"{base}/v1/chat/completions", json=request)
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
            try:
                return _extract_pe_prompt(message.get("content") or "")
            except RuntimeError as exc:
                raise RuntimeError(f"{exc} Resposta: {(message.get('content') or '')[:400]}") from exc
        finally:
            await self._stop()

    def _comfy_command(self) -> list[str]:
        return [
            str(fast._python()), str(fast.COMFY_DIR / "main.py"), "--listen", "127.0.0.1",
            "--base-directory", str(fast.IMAGE_ROOT),
            "--input-directory", str(fast.INPUT_DIR),
            "--output-directory", str(fast.OUTPUT_DIR),
            "--temp-directory", str(fast.TEMP_DIR),
            "--disable-auto-launch", "--preview-method", "none", "--cache-none",
            "--reserve-vram", "0.75", "--disable-metadata",
            *(["--cpu"] if self._cpu_mode else ["--lowvram"] if self._memory_saver else []),
        ]
    async def _start_comfy(self) -> str:
        return await self._start(self._comfy_command(), fast.COMFY_DIR)

    def _reference_size(self, width: int, height: int, model_file: str, index: int, count: int) -> tuple[int, int]:
        if self._memory_saver or (model_file == MODEL_FILE and count >= BALANCED_EDIT_REFERENCES):
            main_budget = 512**2 if self._cpu_mode else REFERENCE_PIXELS
            extra_budget = 512**2 if self._cpu_mode else BALANCED_AUXILIARY_PIXELS
            budget = main_budget if index == 0 else extra_budget / max(1, count - 1)
            side_limit = 512 if self._cpu_mode else MAX_REFERENCE_SIDE
            scale = min(1.0, math.sqrt(budget / (width * height)), side_limit / max(width, height))
            return tuple(max(32, round(side * scale / 32) * 32) for side in (width, height))
        if model_file == EDIT_MODEL_FILE and BALANCED_EDIT_REFERENCES <= count <= MAX_INT8_EDIT_REFERENCES:
            return _fit_balanced_reference(width, height, index, count)
        return _fit_reference(width, height, detailed_edit=model_file == EDIT_MODEL_FILE)

    def _generation_size(self, resolution: str) -> tuple[int, int]:
        size = qwen_image_dimensions(resolution)
        return cpu_image_size(*size) if self._cpu_mode else size

    async def run(
        self, prompt: str, resolution: str, references: list[str], user_id: Optional[str],
        progress: ProgressCallback, dimensions: Optional[DimensionsCallback] = None,
    ) -> str:
        async with self._request_lock:
            return await self._run_recovery(prompt, resolution, references, user_id, progress, dimensions)

    async def _run_recovery(
        self, prompt: str, resolution: str, references: list[str], user_id: Optional[str],
        progress: ProgressCallback, dimensions: Optional[DimensionsCallback] = None,
    ) -> str:
        from neveai.routers.stable_diffusion import _preferred_sd_cpp_windows_backend

        cpu = os.name == "nt" and cpu_image_requested(await asyncio.to_thread(_preferred_sd_cpp_windows_backend))
        report = monotonic_progress(progress)
        seed = random.getrandbits(63)
        # Retry only memory failures; preserve the seed and a successful planner rewrite.
        plans = [(True, True, True)] if cpu else [(False, False, False), (True, False, True), (True, True, True)]
        self._retry_prompt = None
        try:
            for index, (gguf, cpu_mode, saver) in enumerate(plans):
                try:
                    return await self._run_once(prompt, resolution, references, user_id, report, dimensions,
                                                force_gguf=gguf, cpu_mode=cpu_mode, memory_saver=saver, seed=seed)
                except Exception as exc:
                    if not is_image_memory_error(exc) or index == len(plans) - 1:
                        raise
                    log.warning("%s: recuperacao de memoria, tentativa %s: %s", self.NAME, index + 2, exc)
        finally:
            self._retry_prompt = None

    async def _run_once(
        self, prompt: str, resolution: str, references: list[str], user_id: Optional[str],
        progress: ProgressCallback, dimensions: Optional[DimensionsCallback] = None, *,
        force_gguf: bool = False, cpu_mode: bool = False, memory_saver: bool = False, seed: Optional[int] = None,
    ) -> str:
        if not prompt.strip():
            raise ValueError("Descreva a imagem que deseja criar.")
        if len(references) > 10:
            raise ValueError(f"{self.NAME} aceita ate dez imagens de referencia.")
        if os.name != "nt":
            raise RuntimeError(f"{self.NAME} via ComfyUI requer Windows nesta instalacao.")
        async with self._lock:
            uploaded: list[str] = []
            self._force_gguf, self._cpu_mode, self._memory_saver = force_gguf, cpu_mode, memory_saver
            try:
                model_file = await self._ensure_models(progress, bool(references), len(references))
                prepared: list[bytes] = []
                width, height = self._generation_size(resolution)
                for index, reference in enumerate(references):
                    raw = await asyncio.to_thread(_read_image_reference_bytes, reference, user_id)
                    with Image.open(io.BytesIO(raw)) as opened:
                        image = ImageOps.exif_transpose(opened).convert("RGB")
                        size = self._reference_size(*image.size, model_file, index, len(references))
                        if size != image.size:
                            image = image.resize(size, Image.Resampling.LANCZOS)
                        if index == 0:
                            width, height = size
                        output = io.BytesIO()
                        image.save(output, format="PNG")
                        prepared.append(output.getvalue())
                if dimensions is not None:
                    await dimensions(width, height)
                if prepared:
                    if self._retry_prompt is None:
                        self._retry_prompt = await self._plan_edit(prompt, prepared, progress)
                    prompt = self._retry_prompt
                await progress(30)
                base = await self._start_comfy()
                async with httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(30, read=120, write=120, pool=30)) as client:
                    names: list[str] = []
                    for raw in prepared:
                        response = await client.post(
                            "/upload/image",
                            files={"image": (f"neve21_{random.getrandbits(64):016x}.png", raw, "image/png")},
                            data={"type": "input", "overwrite": "false"},
                        )
                        response.raise_for_status()
                        name = response.json()["name"]
                        names.append(name)
                        uploaded.append(name)
                    workflow = self.build_workflow(prompt, width, height, names, seed if seed is not None else random.getrandbits(63), model_file=model_file)
                    if workflow["4"]["class_type"] == "NeveTextEncodeQwenImage21CFG1" and not self._cfg1_node_ready:
                        workflow["4"]["class_type"] = "TextEncodeQwenImage21"
                    client_id = f"neve21-{random.getrandbits(64):016x}"
                    response = await client.post("/prompt", json={"prompt": workflow, "client_id": client_id})
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("node_errors"):
                        raise RuntimeError(f"Workflow {self.NAME} invalido: {payload['node_errors']}")
                    prompt_id = str(payload.get("prompt_id") or "")
                    if not prompt_id:
                        raise RuntimeError("ComfyUI nao retornou identificador da imagem.")
                    await progress(36)
                    last_progress = 36
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None)) as session:
                        websocket = None
                        try:
                            websocket = await session.ws_connect(base.replace("http://", "ws://") + f"/ws?clientId={client_id}", heartbeat=30)
                        except Exception:
                            pass
                        try:
                            for _ in range(10800 if cpu_mode else 1800):
                                if self._process is None or self._process.returncode is not None:
                                    raise RuntimeError("ComfyUI encerrou durante a edicao:\n" + "\n".join(self._log_tail[-25:]))
                                if websocket is not None:
                                    try:
                                        event = await asyncio.wait_for(websocket.receive(), 1)
                                        if event.type == aiohttp.WSMsgType.TEXT:
                                            data = event.json()
                                            item = data.get("data") or {}
                                            if data.get("type") == "progress" and item.get("prompt_id") == prompt_id and item.get("max"):
                                                last_progress = max(last_progress, min(94, 40 + int(54 * item["value"] / item["max"])))
                                    except asyncio.TimeoutError:
                                        pass
                                else:
                                    await asyncio.sleep(1)
                                await progress(last_progress)
                                response = await client.get(f"/history/{prompt_id}")
                                response.raise_for_status()
                                history = response.json().get(prompt_id)
                                if not history:
                                    continue
                                status = history.get("status") or {}
                                if status.get("status_str") == "error":
                                    raise worker_error(self.NAME, status)
                                images = (history.get("outputs") or {}).get("8", {}).get("images") or []
                                if images:
                                    item = images[0]
                                    response = await client.get("/view", params={
                                        "filename": item["filename"], "subfolder": item.get("subfolder", ""),
                                        "type": item.get("type", "output"),
                                    })
                                    response.raise_for_status()
                                    with Image.open(io.BytesIO(response.content)) as generated:
                                        if generated.size != (width, height):
                                            raise RuntimeError(f"{self.NAME} retornou {generated.size}; esperado {(width, height)}.")
                                    output = (fast.OUTPUT_DIR / item.get("subfolder", "") / item["filename"]).resolve()
                                    if output.is_relative_to(fast.OUTPUT_DIR.resolve()):
                                        output.unlink(missing_ok=True)
                                    await progress(99)
                                    return "data:image/png;base64," + base64.b64encode(response.content).decode("ascii")
                            raise RuntimeError(f"{self.NAME} excedeu o tempo limite.")
                        finally:
                            if websocket is not None:
                                await websocket.close()
            finally:
                await self._stop()
                self._force_gguf = self._cpu_mode = self._memory_saver = False
                for name in uploaded:
                    path = (fast.INPUT_DIR / name).resolve()
                    if path.is_relative_to(fast.INPUT_DIR.resolve()):
                        path.unlink(missing_ok=True)


neve_image_21_runtime = NeveImage21Runtime()
