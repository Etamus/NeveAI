"""Local music generation powered by ACE-Step 1.5 Turbo.

ACE-Step runs in its own uv-managed environment so its pinned PyTorch and
Transformers dependencies never mix with the Neve AI backend environment.
The runtime and model cache are prepared lazily on the first generation.
"""

from __future__ import annotations

import asyncio
import json
import logging
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
ACE_STEP_LM_MODEL = "acestep-5Hz-lm-0.6B"
ACE_STEP_LM_REPO = "ACE-Step/acestep-5Hz-lm-0.6B"
ACE_STEP_ARCHIVE_URL = (
    f"https://github.com/ace-step/ACE-Step-1.5/archive/refs/tags/{ACE_STEP_VERSION}.zip"
)
ACE_STEP_RUNTIME_REVISION = "neve-ace-step-1.5-turbo-v1"
PORTUGUESE_MUSIC_INSTRUCTION = (
    "Siga fielmente o pedido do usuário. Preserve o tema, o gênero, o clima, "
    "os instrumentos e todos os detalhes solicitados, sem substituir o assunto "
    "nem acrescentar uma proposta diferente. Quando houver letra ou voz, escreva "
    "e cante exclusivamente em português do Brasil, sem palavras ou trechos em "
    "outro idioma.\n\nPedido do usuário:\n"
)

MUSIC_ROOT = CACHE_DIR / "music_generation"
ACE_STEP_SOURCE_DIR = MUSIC_ROOT / "ACE-Step-1.5"
ACE_STEP_MARKER = ACE_STEP_SOURCE_DIR / ".neve-runtime-ready"
ACE_STEP_HF_CACHE = MUSIC_ROOT / "huggingface"
ACE_STEP_TEMP_DIR = MUSIC_ROOT / "temporary"
ACE_STEP_TRITON_CACHE = MUSIC_ROOT / "triton"
ACE_STEP_TORCH_CACHE = MUSIC_ROOT / "torchinductor"

ProgressCallback = Callable[[str], Awaitable[None]]


def _build_music_generation_request(
    prompt: str, music_plan: Optional[dict] = None
) -> dict:
    request_data = {
        "thinking": music_plan is None,
        "model": ACE_STEP_MODEL,
        "lm_model_path": ACE_STEP_LM_MODEL,
        "lm_backend": "pt",
        "lm_temperature": 0.55,
        "lm_top_p": 0.9,
        "vocal_language": "pt",
        "use_cot_caption": False,
        "use_cot_language": False,
        "inference_steps": 8,
        "batch_size": 1,
        "audio_format": "flac",
    }
    if music_plan:
        instrumental = bool(music_plan.get("instrumental"))
        request_data.update(
            {
                "sample_mode": False,
                "prompt": str(music_plan.get("caption") or prompt).strip(),
                "lyrics": (
                    "[Instrumental]"
                    if instrumental
                    else str(music_plan.get("lyrics") or "").strip()
                ),
            }
        )
    else:
        request_data.update(
            {
                "sample_mode": True,
                "sample_query": f"{PORTUGUESE_MUSIC_INSTRUCTION}{prompt}",
            }
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
        self._log_tail: deque[str] = deque(maxlen=40)
        self._port: Optional[int] = None
        self._cancel_requested = False

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
        while line := await process.stdout.readline():
            decoded = line.decode("utf-8", errors="replace").rstrip()
            output.append(decoded)
            log.debug("ACE-Step setup: %s", decoded)
        return_code = await process.wait()
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
            "pytorch_model.bin",
            "pytorch_model.bin.index.json",
        )
        return any((model_dir / name).is_file() for name in weight_names)

    async def _ensure_lm_model(self, progress: ProgressCallback) -> None:
        model_dir = ACE_STEP_SOURCE_DIR / "checkpoints" / ACE_STEP_LM_MODEL
        if self._has_model_weights(model_dir):
            return

        await progress("Baixando o modelo...")
        download_script = (
            "from huggingface_hub import snapshot_download; "
            f"snapshot_download(repo_id={ACE_STEP_LM_REPO!r}, "
            f"local_dir={str(model_dir)!r}, cache_dir={str(ACE_STEP_HF_CACHE)!r})"
        )
        await self._run_setup_command(
            [str(_runtime_python()), "-c", download_script]
        )
        if not self._has_model_weights(model_dir):
            raise RuntimeError("O download do modelo não foi concluído.")

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
        self, progress: ProgressCallback, initialize_lm: bool = True
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
                "ACESTEP_INIT_LLM": "true" if initialize_lm else "false",
                "ACESTEP_LM_MODEL_PATH": ACE_STEP_LM_MODEL,
                "ACESTEP_LM_BACKEND": "pt",
                "ACESTEP_DOWNLOAD_SOURCE": "huggingface",
                "ACESTEP_NO_INIT": "true",
                "ACESTEP_CHECK_UPDATE": "false",
                "HF_HOME": str(ACE_STEP_HF_CACHE),
                "ACESTEP_TMPDIR": str(ACE_STEP_TEMP_DIR),
                "TRITON_CACHE_DIR": str(ACE_STEP_TRITON_CACHE),
                "TORCHINDUCTOR_CACHE_DIR": str(ACE_STEP_TORCH_CACHE),
            }
        )

        await progress("Iniciando o gerador de música...")
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
        music_plan: Optional[dict] = None,
    ) -> dict:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Descreva a música que deseja criar.")

        async with self._generation_lock:
            await self.ensure_installed(progress)
            if music_plan is None:
                await self._ensure_lm_model(progress)
            try:
                base_url = await self._start_server(
                    progress, initialize_lm=music_plan is None
                )
                await progress("Carregando o modelo...")
                timeout = httpx.Timeout(connect=15, read=120, write=30, pool=15)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    release_response = await client.post(
                        f"{base_url}/release_task",
                        json=_build_music_generation_request(prompt, music_plan),
                        # The first request loads (and may download) both model tiers
                        # before returning its task id. Keep connection limits, but do
                        # not abort a healthy first-time setup because of its duration.
                        timeout=httpx.Timeout(connect=15, read=None, write=30, pool=15),
                    )
                    release_response.raise_for_status()
                    release_data = self._unwrap(release_response.json())
                    if not isinstance(release_data, dict) or not release_data.get("task_id"):
                        raise RuntimeError("ACE-Step não retornou um identificador de tarefa.")
                    task_id = str(release_data["task_id"])

                    last_description = ""
                    for _ in range(1800):
                        if self._cancel_requested:
                            raise asyncio.CancelledError
                        await asyncio.sleep(2)
                        query_response = await client.post(
                            f"{base_url}/query_result",
                            json={"task_id_list": [task_id]},
                        )
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
                            f"Gerando música... {max(0, min(percent, 100))}%"
                            if percent is not None
                            else "Gerando música..."
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
                            "content_type": audio_response.headers.get("content-type", "audio/mpeg").split(";", 1)[0],
                            "prompt": str(generated.get("prompt") or prompt),
                            "lyrics": str(generated.get("lyrics") or ""),
                            "metadata": generated.get("metas") if isinstance(generated.get("metas"), dict) else {},
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
