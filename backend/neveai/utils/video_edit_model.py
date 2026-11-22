"""Private llama.cpp worker for Neve Studio; never registered as a chat model."""
import asyncio
import logging
import os
import platform
import secrets
import socket
import subprocess
import tempfile
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial

import httpx
import psutil
from fastapi import HTTPException

from neveai.config import DATA_DIR
from neveai.utils.model_availability import media_is_busy
from neveai.utils.video_edit_weights import MODEL_NAME, local_weights, weights_dir
from neveai.utils.voice_priority import primary_gpu_work

log = logging.getLogger(__name__)
GIB = 1024 ** 3
ALIAS = "neve-maker"
GPU_CONTEXT = 16384
CPU_CONTEXT = 8192


def _port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _command(binary, model, projector, port, key, gpu):
    cmd = [str(binary), "--model", str(model), "--mmproj", str(projector),
           "--host", "127.0.0.1", "--port", str(port), "--api-key", key, "--alias", ALIAS,
           "--parallel", "1", "--n-gpu-layers", "all" if gpu else "0",
           "--ctx-size", str(GPU_CONTEXT if gpu else CPU_CONTEXT),
           "--threads", str(min(6, max(1, (os.cpu_count() or 4) // 2))),
           "--no-webui", "--fit", "off", "--jinja"]
    if not gpu:
        cmd += ["--device", "none", "--no-mmproj-offload"]
    return cmd


async def _wait_ready(process, client):
    async with asyncio.timeout(120):
        while process.returncode is None:
            try:
                reply = await client.get("/v1/models", timeout=1.5)
                if reply.is_success and any(item.get("id") == ALIAS for item in reply.json().get("data", [])):
                    return
            except (httpx.TransportError, ValueError):
                pass
            await asyncio.sleep(.25)
    raise RuntimeError("Neve Studio worker stopped during startup")


async def _stop(process):
    if process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), 6)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


@asynccontextmanager
async def _worker(binary, model, projector, gpu):
    port, key = _port(), secrets.token_hex(24)
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLAMA_ARG_")}
    env["PATH"] = str(binary.parent) + os.pathsep + env.get("PATH", "")
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    with tempfile.TemporaryFile() as log_file:
        process = await asyncio.create_subprocess_exec(*_command(binary, model, projector, port, key, gpu),
            cwd=binary.parent, env=env, stdout=log_file, stderr=asyncio.subprocess.STDOUT, **flags)
        try:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False,
                    headers={"Authorization": f"Bearer {key}"}, timeout=150) as client:
                try:
                    await _wait_ready(process, client)
                except (RuntimeError, TimeoutError):
                    log_file.seek(0, os.SEEK_END)
                    log_file.seek(max(0, log_file.tell() - 2400))
                    log.warning("Neve Studio worker startup (%s): %s", "GPU" if gpu else "CPU",
                                log_file.read().decode("utf-8", errors="replace"))
                    raise

                async def complete(messages, *, no_think=True, **options):
                    response = await client.post("/v1/chat/completions", json={
                        "model": ALIAS, "messages": messages, "stream": False,
                        "chat_template_kwargs": {"enable_thinking": not no_think},
                        **options,
                    })
                    response.raise_for_status()
                    return response.json()

                yield {"filename": MODEL_NAME, "n_ctx": GPU_CONTEXT if gpu else CPU_CONTEXT}, complete
        finally:
            await _stop(process)


@asynccontextmanager
async def director_model(progress):
    from neveai.routers.llamacpp import LLAMACPP_SERVER_BIN, _get_vram_info
    from neveai.utils.middleware import _MEDIA_GENERATION_LOCK

    try:
        model, projector = local_weights(weights_dir(DATA_DIR))
    except OSError as exc:
        raise HTTPException(503, "The Neve Studio weights are missing. Run the NeveAI installer or repair to prepare them.") from exc
    if not LLAMACPP_SERVER_BIN.is_file():
        raise HTTPException(503, "The Neve Studio runtime is missing. Run the NeveAI installer or repair.")

    memory = await asyncio.to_thread(_get_vram_info)
    gpu = (any(item["free"] >= 10 * GIB for item in memory.get("gpus", []))
           or (platform.system() == "Darwin" and platform.machine() == "arm64" and psutil.virtual_memory().available >= 12 * GIB))
    worker = partial(_worker, LLAMACPP_SERVER_BIN, model, projector)
    if gpu and not media_is_busy() and not _MEDIA_GENERATION_LOCK.locked():
        async with _MEDIA_GENERATION_LOCK, primary_gpu_work():
            if not media_is_busy():
                progress("Loading the Neve Studio model on GPU...")
                async with AsyncExitStack() as stack:
                    try:
                        session = await stack.enter_async_context(worker(gpu=True))
                    except (OSError, RuntimeError, TimeoutError):
                        log.info("Neve Studio could not start on GPU; trying CPU", exc_info=True)
                    else:
                        yield session
                        return
    if psutil.virtual_memory().available < 7 * GIB:
        raise HTTPException(503, "Neve Studio needs more free memory. Close other applications and try again.")
    progress("Loading the Neve Studio model on CPU...")
    async with worker(gpu=False) as session:
        yield session
