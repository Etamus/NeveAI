"""Local music generation powered by ACE-Step 1.5 Turbo.

ACE-Step runs in its own uv-managed environment so its pinned PyTorch and
Transformers dependencies never mix with the NeveAI backend environment.
The runtime and model cache are prepared lazily on the first generation.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
import json
import logging
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import zipfile
from collections import deque
from pathlib import Path
from typing import Awaitable, Callable, Optional
from urllib.request import Request as UrlRequest, urlopen

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from neveai.config import CACHE_DIR
from neveai.constants import ERROR_MESSAGES
from neveai.utils.access_control import has_permission
from neveai.utils.auth import get_verified_user

log = logging.getLogger(__name__)
router = APIRouter()

ACE_STEP_VERSION = "v0.1.8"
ACE_STEP_MODEL = "acestep-v15-turbo"
ACE_STEP_MAIN_REPO = "ACE-Step/Ace-Step1.5"
ACE_STEP_ARCHIVE_URL = (
    f"https://github.com/ace-step/ACE-Step-1.5/archive/refs/tags/{ACE_STEP_VERSION}.zip"
)
ACE_STEP_RUNTIME_REVISION = "neve-ace-step-1.5-turbo-v1"
MUSIC_ROOT = CACHE_DIR / "music_generation"
ACE_STEP_SOURCE_DIR = MUSIC_ROOT / "ACE-Step-1.5"
ACE_STEP_MARKER = ACE_STEP_SOURCE_DIR / ".neve-runtime-ready"
ACE_STEP_HF_CACHE = MUSIC_ROOT / "huggingface"
ACE_STEP_TEMP_DIR = MUSIC_ROOT / "temporary"
ACE_STEP_TRITON_CACHE = MUSIC_ROOT / "triton"
ACE_STEP_TORCH_CACHE = MUSIC_ROOT / "torchinductor"

ProgressCallback = Callable[[str], Awaitable[None]]


def _normalize_search_text(value: str) -> str:
    import unicodedata

    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )


def _parse_repaint_range(prompt: str) -> tuple[Optional[float], Optional[float]]:
    def seconds(value: str) -> float:
        parts = [float(part.replace(",", ".")) for part in value.split(":")]
        total = 0.0
        for part in parts:
            total = total * 60 + part
        return total

    clock_values = re.findall(r"(?<!\d)(\d{1,2}(?::\d{1,2}){1,2})(?!\d)", prompt)
    if len(clock_values) >= 2:
        return seconds(clock_values[0]), seconds(clock_values[1])

    normalized = _normalize_search_text(prompt)
    match = re.search(
        r"(?:de|entre|from|between)\s+(\d+(?:[.,]\d+)?)\s*(?:s|segundos?|seconds?)?\s+"
        r"(?:a|ate|e|to|and)\s+(\d+(?:[.,]\d+)?)\s*(?:s|segundos?|seconds?)?",
        normalized,
    )
    if match:
        return float(match.group(1).replace(",", ".")), float(
            match.group(2).replace(",", ".")
        )
    return None, None


def infer_music_audio_plan(prompt: str, audio_count: int) -> dict:
    """Map natural-language audio requests to ACE-Step's native task types."""
    if audio_count <= 0:
        return {"task_type": "text2music"}

    normalized = _normalize_search_text(prompt)
    repaint_start, repaint_end = _parse_repaint_range(prompt)
    explicit_repaint_terms = (
        "repaint",
        "retake",
    )
    reference_terms = (
        "reference audio",
        "audio de referencia",
        "como referencia",
        "usar de referencia",
        "use de referencia",
        "minha voz",
        "essa voz",
        "esta voz",
        "mesma voz",
        "voz do audio",
        "voz deste audio",
        "voz desse audio",
        "meu timbre",
        "esse timbre",
        "este timbre",
        "clonar a voz",
        "clone a voz",
        "cantada com essa voz",
        "cantada com esta voz",
    )

    if any(term in normalized for term in explicit_repaint_terms) or (
        repaint_start is not None and repaint_end is not None
    ):
        plan = {
            "task_type": "repaint",
            "chunk_mask_mode": (
                "explicit"
                if repaint_start is not None and repaint_end is not None
                else "auto"
            ),
            "repaint_mode": "balanced",
            "repaint_strength": 0.5,
        }
        if (
            repaint_start is not None
            and repaint_end is not None
            and repaint_end > repaint_start
        ):
            plan["repainting_start"] = repaint_start
            plan["repainting_end"] = repaint_end
        return plan

    if any(term in normalized for term in reference_terms):
        return {"task_type": "text2music", "uses_reference_audio": True}

    replace_entire_lyrics = any(
        term in normalized
        for term in (
            "troque a letra inteira",
            "trocar a letra inteira",
            "substitua a letra inteira",
            "substituir a letra inteira",
            "mude a letra inteira",
            "mudar a letra inteira",
            "replace the entire lyrics",
            "replace all lyrics",
        )
    )
    preserve_source = any(
        term in normalized
        for term in (
            "mantenha",
            "matenha",
            "manter",
            "preserve",
            "preservar",
            "sem mudar",
            "nao mude",
            "mesma musica",
            "mesma melodia",
            "apenas a letra",
            "somente a letra",
            "so a letra",
        )
    )
    style_change = any(
        term in normalized
        for term in (
            "transforme em",
            "mude o estilo",
            "troque o estilo",
            "remix",
            "remixe",
        )
    )
    if replace_entire_lyrics:
        # Keep every diffusion step structurally conditioned. A moderate source
        # latent blend preserves the voice and arrangement without letting the
        # original vocal overpower the replacement lyrics.
        cover_strength, noise_strength = 1.0, 0.4
    elif preserve_source:
        cover_strength, noise_strength = 1.0, 0.75
    elif style_change:
        cover_strength, noise_strength = 0.75, 0.25
    else:
        cover_strength, noise_strength = 0.9, 0.5
    return {
        "task_type": "cover",
        "audio_cover_strength": cover_strength,
        "cover_noise_strength": noise_strength,
        "preserve_source": preserve_source or replace_entire_lyrics,
        "replace_entire_lyrics": replace_entire_lyrics,
    }


def _build_music_generation_request(
    prompt: str,
    music_plan: dict,
    audio_plan: Optional[dict] = None,
    lm_model: Optional[str] = None,
) -> dict:
    audio_plan = audio_plan or {"task_type": "text2music"}
    task_type = str(audio_plan.get("task_type") or "text2music")
    instrumental = bool(music_plan.get("instrumental"))
    lyrics = "" if instrumental else str(music_plan.get("lyrics") or "").strip()
    request_data = {
        "thinking": bool(lm_model) and task_type == "text2music",
        "model": ACE_STEP_MODEL,
        "vocal_language": "pt",
        "use_cot_caption": False,
        "use_cot_language": False,
        "inference_steps": 8,
        "batch_size": 1,
        "audio_format": "flac",
        "sample_mode": False,
        "prompt": str(music_plan.get("caption") or prompt).strip(),
        "lyrics": "[Instrumental]" if instrumental else lyrics,
        "task_type": task_type,
    }
    if lm_model and task_type == "text2music":
        request_data.update({"lm_model_path": lm_model, "lm_backend": "pt"})
    for key in (
        "audio_cover_strength",
        "cover_noise_strength",
        "repainting_start",
        "repainting_end",
        "chunk_mask_mode",
        "repaint_mode",
        "repaint_strength",
    ):
        if key in audio_plan:
            request_data[key] = audio_plan[key]
    if task_type == "repaint":
        request_data.update(
            {
                "repaint_latent_crossfade_frames": 10,
                "repaint_wav_crossfade_sec": 0.15,
            }
        )
    if lyrics and task_type == "text2music":
        lyric_lines = [
            line.strip()
            for line in lyrics.splitlines()
            if line.strip()
            and not (line.strip().startswith("[") and line.strip().endswith("]"))
        ]
        word_count = sum(
            len(re.findall(r"\b\w+\b", line, flags=re.UNICODE))
            for line in lyric_lines
        )
        section_count = sum(
            line.strip().startswith("[") and line.strip().endswith("]")
            for line in lyrics.splitlines()
        )
        # Avoid forcing long supplied lyrics into the implicit one-minute target.
        request_data["audio_duration"] = round(
            max(45.0, min(360.0, word_count / 2.1 + min(section_count, 16) * 1.5)),
            1,
        )
    return request_data


def _hidden_process_kwargs() -> dict:
    if os.name != "nt":
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}


def _runtime_python() -> Path:
    if os.name == "nt":
        return ACE_STEP_SOURCE_DIR / ".venv" / "Scripts" / "python.exe"
    return ACE_STEP_SOURCE_DIR / ".venv" / "bin" / "python"


def _download_archive(destination: Path) -> None:
    request = UrlRequest(
        ACE_STEP_ARCHIVE_URL,
        headers={"User-Agent": "NeveAI-ACE-Step/1.0"},
    )
    with urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)


def _extract_archive(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as package:
        destination_root = destination.resolve()
        for member in package.infolist():
            member_path = (destination / member.filename).resolve()
            if destination_root != member_path and destination_root not in member_path.parents:
                raise RuntimeError("O pacote do ACE-Step contém um caminho inválido.")
        package.extractall(destination)


def _replace_source_from_archive() -> None:
    MUSIC_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ace-step-", dir=MUSIC_ROOT) as temporary:
        temporary_dir = Path(temporary)
        archive = temporary_dir / "ace-step.zip"
        extracted = temporary_dir / "extracted"
        extracted.mkdir()
        _download_archive(archive)
        _extract_archive(archive, extracted)

        roots = [item for item in extracted.iterdir() if item.is_dir()]
        if len(roots) != 1 or not (roots[0] / "pyproject.toml").is_file():
            raise RuntimeError("O pacote baixado do ACE-Step não possui a estrutura esperada.")

        if ACE_STEP_SOURCE_DIR.exists():
            shutil.rmtree(ACE_STEP_SOURCE_DIR)
        shutil.move(str(roots[0]), str(ACE_STEP_SOURCE_DIR))


class AceStepRuntime:
    def __init__(self) -> None:
        self._runtime_lock = asyncio.Lock()
        self._generation_lock = asyncio.Lock()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._log_task: Optional[asyncio.Task] = None
        self._log_tail: deque[str] = deque(maxlen=120)
        self._port: Optional[int] = None
        self._cancel_requested = False
        self._detected_lm_model: Optional[str] = None
        self._lm_detection_complete = False

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def is_installed(self) -> bool:
        if not ACE_STEP_MARKER.is_file() or not _runtime_python().is_file():
            return False
        try:
            return ACE_STEP_MARKER.read_text(encoding="utf-8").strip() == ACE_STEP_RUNTIME_REVISION
        except OSError:
            return False

    async def _run_setup_command(self, args: list[str]) -> None:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(ACE_STEP_SOURCE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **_hidden_process_kwargs(),
        )
        output: deque[str] = deque(maxlen=35)
        assert process.stdout is not None
        try:
            while line := await process.stdout.readline():
                decoded = line.decode("utf-8", errors="replace").rstrip()
                output.append(decoded)
                log.debug("ACE-Step setup: %s", decoded)
            return_code = await process.wait()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            raise
        if return_code != 0:
            details = "\n".join(output)
            raise RuntimeError(
                "Não foi possível preparar o ambiente do ACE-Step."
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

        await self._run_setup_command(
            [sys.executable, "-m", "pip", "install", "uv>=0.8,<1"]
        )

    async def ensure_installed(self, progress: ProgressCallback) -> None:
        if self.is_installed:
            return

        async with self._runtime_lock:
            if self.is_installed:
                return
            if sys.version_info[:2] not in {(3, 11), (3, 12)}:
                raise RuntimeError("ACE-Step requer Python 3.11 ou 3.12.")

            await progress("Preparando o gerador de música...")
            await asyncio.to_thread(_replace_source_from_archive)
            await progress("Instalando o ambiente isolado...")
            await self._ensure_uv()

            command = [
                sys.executable,
                "-m",
                "uv",
                "sync",
                "--project",
                str(ACE_STEP_SOURCE_DIR),
                "--python",
                sys.executable,
                "--no-dev",
                "--no-progress",
            ]
            if (ACE_STEP_SOURCE_DIR / "uv.lock").is_file():
                command.append("--frozen")
            await self._run_setup_command(command)

            ACE_STEP_MARKER.write_text(ACE_STEP_RUNTIME_REVISION, encoding="utf-8")

    @staticmethod
    def _has_model_weights(model_dir: Path) -> bool:
        if not model_dir.is_dir():
            return False
        weight_names = (
            "model.safetensors",
            "model.safetensors.index.json",
            "diffusion_pytorch_model.safetensors",
            "pytorch_model.bin",
            "pytorch_model.bin.index.json",
        )
        return any((model_dir / name).is_file() for name in weight_names)

    @classmethod
    def _generation_component_ready(cls, model_dir: Path) -> bool:
        return (model_dir / "config.json").is_file() and cls._has_model_weights(
            model_dir
        )

    async def _detect_recommended_lm_model(self) -> Optional[str]:
        if self._lm_detection_complete:
            return self._detected_lm_model
        script = (
            "from acestep.gpu_config import get_global_gpu_config, get_recommended_lm_model; "
            "m=get_recommended_lm_model(get_global_gpu_config()); "
            "print('NEVE_LM_MODEL=' + (m or ''))"
        )
        process = await asyncio.create_subprocess_exec(
            str(_runtime_python()),
            "-c",
            script,
            cwd=str(ACE_STEP_SOURCE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **_hidden_process_kwargs(),
        )
        output, _ = await process.communicate()
        match = re.search(
            r"^NEVE_LM_MODEL=(.*)$",
            output.decode("utf-8", errors="replace"),
            re.MULTILINE,
        )
        if process.returncode == 0 and match:
            model = match.group(1).strip()
            self._detected_lm_model = model or None
        else:
            log.warning(
                "ACE-Step LM hardware detection failed; continuing without the music LM"
            )
        self._lm_detection_complete = True
        return self._detected_lm_model

    async def _ensure_generation_models(
        self, progress: ProgressCallback, lm_model: Optional[str] = None
    ) -> None:
        required_dirs = [
            ACE_STEP_SOURCE_DIR / "checkpoints" / ACE_STEP_MODEL,
            ACE_STEP_SOURCE_DIR / "checkpoints" / "Qwen3-Embedding-0.6B",
            ACE_STEP_SOURCE_DIR / "checkpoints" / "vae",
        ]
        if lm_model:
            required_dirs.append(ACE_STEP_SOURCE_DIR / "checkpoints" / lm_model)
        if all(self._generation_component_ready(path) for path in required_dirs):
            return

        await progress("Baixando o modelo...")
        checkpoints_dir = ACE_STEP_SOURCE_DIR / "checkpoints"
        patterns = [
            "config.json",
            f"{ACE_STEP_MODEL}/*",
            "Qwen3-Embedding-0.6B/*",
            "vae/*",
        ]
        if lm_model:
            patterns.append(f"{lm_model}/*")
        download_script = (
            "from huggingface_hub import snapshot_download; "
            f"snapshot_download(repo_id={ACE_STEP_MAIN_REPO!r}, "
            f"local_dir={str(checkpoints_dir)!r}, "
            f"allow_patterns={patterns!r})"
        )
        initial_size = await asyncio.to_thread(self._directory_size, checkpoints_dir)
        download_task = asyncio.create_task(
            self._run_setup_command([str(_runtime_python()), "-c", download_script])
        )
        last_size = initial_size
        try:
            while not download_task.done():
                done, _ = await asyncio.wait({download_task}, timeout=2)
                if done:
                    break
                current_size = await asyncio.to_thread(
                    self._directory_size, checkpoints_dir
                )
                if current_size > last_size:
                    downloaded = current_size - initial_size
                    await progress(
                        f"Baixando o modelo... {self._format_size(downloaded)}"
                    )
                    last_size = current_size
            await download_task
        finally:
            if not download_task.done():
                download_task.cancel()
                try:
                    await download_task
                except asyncio.CancelledError:
                    pass
        if not all(self._generation_component_ready(path) for path in required_dirs):
            raise RuntimeError("O download dos componentes do modelo não foi concluído.")

    @staticmethod
    def _directory_size(directory: Path) -> int:
        if not directory.exists():
            return 0
        total = 0
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                try:
                    total += (Path(root) / filename).stat().st_size
                except OSError:
                    pass
        return total

    @staticmethod
    def _format_size(size: int) -> str:
        if size >= 1024**3:
            return f"{size / 1024**3:.1f} GB"
        return f"{size / 1024**2:.0f} MB"

    @staticmethod
    def _available_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    async def _capture_process_output(
        self,
        process: asyncio.subprocess.Process,
        progress: ProgressCallback,
    ) -> None:
        if process.stdout is None:
            return
        reported_download = False
        while line := await process.stdout.readline():
            decoded = line.decode("utf-8", errors="replace").rstrip()
            self._log_tail.append(decoded)
            log.debug("ACE-Step: %s", decoded)
            lowered = decoded.lower()
            if not reported_download and any(
                marker in lowered
                for marker in ("downloading", "download model", "fetching", "snapshot_download")
            ):
                reported_download = True
                await progress("Baixando o modelo...")

    async def _start_server(
        self, progress: ProgressCallback, lm_model: Optional[str] = None
    ) -> str:
        await self._stop_server()
        self._cancel_requested = False
        self._log_tail.clear()
        self._port = self._available_port()

        for directory in (
            ACE_STEP_HF_CACHE,
            ACE_STEP_TEMP_DIR,
            ACE_STEP_TRITON_CACHE,
            ACE_STEP_TORCH_CACHE,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.update(
            {
                "PYTHONIOENCODING": "utf-8",
                "ACESTEP_API_HOST": "127.0.0.1",
                "ACESTEP_API_PORT": str(self._port),
                "ACESTEP_API_WORKERS": "1",
                "ACESTEP_QUEUE_WORKERS": "1",
                "ACESTEP_QUEUE_MAXSIZE": "1",
                "ACESTEP_CONFIG_PATH": ACE_STEP_MODEL,
                "ACESTEP_INIT_LLM": "true" if lm_model else "false",
                "ACESTEP_LM_MODEL_PATH": lm_model or "",
                "ACESTEP_LM_BACKEND": "pt",
                "ACESTEP_LM_OFFLOAD_TO_CPU": "true",
                "ACESTEP_DOWNLOAD_SOURCE": "huggingface",
                "ACESTEP_NO_INIT": "true",
                "ACESTEP_CHECK_UPDATE": "false",
                "HF_HOME": str(ACE_STEP_HF_CACHE),
                "ACESTEP_TMPDIR": str(ACE_STEP_TEMP_DIR),
                "TRITON_CACHE_DIR": str(ACE_STEP_TRITON_CACHE),
                "TORCHINDUCTOR_CACHE_DIR": str(ACE_STEP_TORCH_CACHE),
            }
        )

        await progress("Iniciando o criador de música...")
        self._process = await asyncio.create_subprocess_exec(
            str(_runtime_python()),
            "-m",
            "acestep.api_server",
            cwd=str(ACE_STEP_SOURCE_DIR),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **_hidden_process_kwargs(),
        )
        self._log_task = asyncio.create_task(
            self._capture_process_output(self._process, progress)
        )

        base_url = f"http://127.0.0.1:{self._port}"
        async with httpx.AsyncClient(timeout=2.0) as client:
            for _ in range(600):
                if self._process.returncode is not None:
                    details = "\n".join(self._log_tail)
                    raise RuntimeError(
                        "ACE-Step encerrou durante a inicialização."
                        + (f"\n{details}" if details else "")
                    )
                try:
                    response = await client.get(f"{base_url}/health")
                    if response.is_success:
                        return base_url
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)

        raise RuntimeError("ACE-Step não respondeu dentro do tempo esperado.")

    async def _stop_server(self) -> None:
        process = self._process
        self._process = None
        self._port = None
        if process is not None and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        if self._log_task is not None:
            try:
                await asyncio.wait_for(self._log_task, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._log_task.cancel()
            self._log_task = None

    async def cancel(self) -> None:
        self._cancel_requested = True
        await self._stop_server()

    @staticmethod
    def _unwrap(payload: dict) -> object:
        if payload.get("code", 200) != 200 or payload.get("error"):
            raise RuntimeError(str(payload.get("error") or "O ACE-Step retornou um erro."))
        return payload.get("data")

    async def generate(
        self,
        prompt: str,
        progress: ProgressCallback,
        music_plan: dict,
        audio_plan: Optional[dict] = None,
        audio_attachments: Optional[list[dict]] = None,
    ) -> dict:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Descreva a música que deseja criar.")

        async with self._generation_lock:
            await self.ensure_installed(progress)
            audio_plan = audio_plan or {"task_type": "text2music"}
            audio_attachments = audio_attachments or []
            task_type = str(audio_plan.get("task_type") or "text2music")
            use_music_lm = task_type == "text2music"
            lm_model = (
                await self._detect_recommended_lm_model() if use_music_lm else None
            )
            await self._ensure_generation_models(progress, lm_model=lm_model)
            try:
                base_url = await self._start_server(progress, lm_model=lm_model)
                await progress("Carregando o modelo...")
                timeout = httpx.Timeout(connect=15, read=120, write=30, pool=15)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    request_data = _build_music_generation_request(
                        prompt, music_plan, audio_plan=audio_plan, lm_model=lm_model
                    )
                    request_timeout = httpx.Timeout(
                        connect=15, read=None, write=120, pool=15
                    )
                    if audio_attachments:
                        with ExitStack() as stack:
                            upload_files = {}
                            source = audio_attachments[0]
                            if task_type in {"cover", "repaint"}:
                                upload_files["src_audio"] = (
                                    source["name"],
                                    stack.enter_context(Path(source["path"]).open("rb")),
                                    source.get("content_type")
                                    or mimetypes.guess_type(source["name"])[0]
                                    or "application/octet-stream",
                                )
                                if len(audio_attachments) > 1:
                                    reference = audio_attachments[1]
                                    upload_files["reference_audio"] = (
                                        reference["name"],
                                        stack.enter_context(
                                            Path(reference["path"]).open("rb")
                                        ),
                                        reference.get("content_type")
                                        or mimetypes.guess_type(reference["name"])[0]
                                        or "application/octet-stream",
                                    )
                            elif audio_plan.get("uses_reference_audio"):
                                upload_files["reference_audio"] = (
                                    source["name"],
                                    stack.enter_context(Path(source["path"]).open("rb")),
                                    source.get("content_type")
                                    or mimetypes.guess_type(source["name"])[0]
                                    or "application/octet-stream",
                                )
                            form_data = {
                                key: (
                                    str(value).lower()
                                    if isinstance(value, bool)
                                    else str(value)
                                )
                                for key, value in request_data.items()
                                if value is not None
                            }
                            release_response = await client.post(
                                f"{base_url}/release_task",
                                data=form_data,
                                files=upload_files or None,
                                timeout=request_timeout,
                            )
                    else:
                        release_response = await client.post(
                            f"{base_url}/release_task",
                            json=request_data,
                            timeout=request_timeout,
                        )
                    release_response.raise_for_status()
                    release_data = self._unwrap(release_response.json())
                    if not isinstance(release_data, dict) or not release_data.get("task_id"):
                        raise RuntimeError("ACE-Step não retornou um identificador de tarefa.")
                    task_id = str(release_data["task_id"])

                    last_description = ""
                    consecutive_transport_errors = 0
                    for _ in range(1800):
                        if self._cancel_requested:
                            raise asyncio.CancelledError
                        await asyncio.sleep(2)
                        try:
                            query_response = await client.post(
                                f"{base_url}/query_result",
                                json={"task_id_list": [task_id]},
                            )
                            consecutive_transport_errors = 0
                        except httpx.TransportError as exc:
                            process = self._process
                            if process is not None and process.returncode is None:
                                consecutive_transport_errors += 1
                                if consecutive_transport_errors < 5:
                                    log.warning(
                                        "ACE-Step query connection interrupted; retrying (%s/4): %r",
                                        consecutive_transport_errors,
                                        exc,
                                    )
                                    await asyncio.sleep(1)
                                    continue

                            sidecar_log = "\n".join(self._log_tail)
                            runtime_errors = re.findall(
                                r"(?:RuntimeError|OSError|Error):\s*([^\r\n]+)",
                                sidecar_log,
                            )
                            detail = runtime_errors[-1] if runtime_errors else ""
                            if process is not None and process.returncode is not None:
                                message = (
                                    "ACE-Step encerrou durante a geração "
                                    f"(código {process.returncode})."
                                )
                            else:
                                message = (
                                    "A comunicação com o ACE-Step foi interrompida "
                                    "durante a geração."
                                )
                            raise RuntimeError(f"{message} {detail}".strip()) from exc
                        query_response.raise_for_status()
                        query_data = self._unwrap(query_response.json())
                        if not isinstance(query_data, list) or not query_data:
                            continue

                        task = query_data[0] if isinstance(query_data[0], dict) else {}
                        status = int(task.get("status", 0))
                        raw_description = str(
                            task.get("progress_text")
                            or task.get("stage")
                            or ""
                        ).strip()
                        progress_value = task.get("progress")
                        percent: Optional[int] = None
                        if isinstance(progress_value, (int, float)):
                            normalized = float(progress_value)
                            percent = round(normalized * 100 if normalized <= 1 else normalized)
                        elif raw_description:
                            match = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*%", raw_description)
                            if match:
                                percent = round(float(match.group(1).replace(",", ".")))
                        description = (
                            f"Criando música... {max(0, min(percent, 100))}%"
                            if percent is not None
                            else "Criando música..."
                        )
                        if description and description != last_description:
                            last_description = description
                            await progress(description)

                        if status == 2:
                            task_error = str(task.get("error") or task.get("message") or "").strip()
                            if not task_error:
                                sidecar_log = "\n".join(self._log_tail)
                                runtime_errors = re.findall(
                                    r"(?:RuntimeError|OSError):\s*([^\r\n]+)",
                                    sidecar_log,
                                )
                                task_error = runtime_errors[-1] if runtime_errors else "Falha ao gerar a música."
                            raise RuntimeError(task_error)
                        if status != 1:
                            continue

                        result = task.get("result")
                        if isinstance(result, str):
                            result = json.loads(result)
                        if not isinstance(result, list) or not result or not isinstance(result[0], dict):
                            raise RuntimeError("ACE-Step concluiu sem retornar um arquivo de áudio.")
                        generated = result[0]
                        audio_paths = generated.get("audio_paths")
                        first_audio_path = (
                            audio_paths[0]
                            if isinstance(audio_paths, list) and audio_paths
                            else ""
                        )
                        audio_url = str(
                            generated.get("first_audio_path")
                            or first_audio_path
                            or generated.get("file")
                            or ""
                        )
                        if not audio_url:
                            raise RuntimeError("ACE-Step concluiu sem retornar o endereço do áudio.")
                        if audio_url.startswith("/"):
                            audio_url = f"{base_url}{audio_url}"

                        audio_response = await client.get(audio_url)
                        audio_response.raise_for_status()
                        return {
                            "audio": audio_response.content,
                            "content_type": audio_response.headers.get(
                                "content-type", "audio/mpeg"
                            ).split(";", 1)[0],
                            "prompt": str(generated.get("prompt") or prompt),
                            "lyrics": str(generated.get("lyrics") or ""),
                            "metadata": (
                                generated.get("metas")
                                if isinstance(generated.get("metas"), dict)
                                else {}
                            ),
                            "task_type": task_type,
                        }

                raise RuntimeError("A geração de música excedeu o tempo limite.")
            except Exception:
                if self._cancel_requested:
                    raise asyncio.CancelledError
                raise
            finally:
                await self._stop_server()


ace_step_runtime = AceStepRuntime()


@router.get("/status")
async def get_music_generation_status(
    request: Request, user=Depends(get_verified_user)
):
    return {
        "enabled": request.app.state.config.ENABLE_MUSIC_GENERATION,
        "installed": ace_step_runtime.is_installed,
        "running": ace_step_runtime.is_running,
        "model": ACE_STEP_MODEL,
    }


@router.post("/cancel")
async def cancel_music_generation(
    request: Request, user=Depends(get_verified_user)
):
    if not has_permission(
        user.id,
        "features.music_generation",
        request.app.state.config.USER_PERMISSIONS,
    ):
        raise HTTPException(status_code=403, detail=ERROR_MESSAGES.ACCESS_PROHIBITED)
    await ace_step_runtime.cancel()
    return {"success": True}
