"""
Local GGUF Model Router — llama-server (llama.cpp) with CUDA/NVIDIA support.

Manages the llama-server.exe subprocess to load/unload GGUF models from the
`models/` directory, exposes them as OpenAI-compatible models, and proxies
chat completions through the llama-server API.
"""

import os
import re
import sys
import time
import json
import base64
import signal
import logging
import asyncio
import mimetypes
import subprocess
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from neveai.env import SRC_LOG_LEVELS, GLOBAL_LOG_LEVEL, BASE_DIR
from neveai.models.models import Models
from neveai.utils.payload import apply_model_params_to_body_openai, apply_system_prompt_to_body

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS.get("MODELS", GLOBAL_LOG_LEVEL))

router = APIRouter()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Separate directory for mmproj (vision encoder) files
MMPROJ_DIR = BASE_DIR / "mmproj"
MMPROJ_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# mmproj compatibility helpers
# ---------------------------------------------------------------------------

def _model_base_name(filename: str) -> str:
    """Extract a comparable base name from a .gguf (model or mmproj) filename."""
    name = Path(filename).stem.lower()
    # Remove quantization suffixes like -q4_k_m, -q5_0, -f16, -BF16, etc.
    name = re.sub(r'[-_.][qQfFbBiI][0-9][0-9a-z_]*$', '', name)
    # Remove "-mmproj" and anything after (e.g. "-mmproj-f16", "-mmproj-model")
    name = re.sub(r'[-_.]?mmproj.*$', '', name)
    # Remove "mmproj" prefix
    name = re.sub(r'^mmproj[-_.]?', '', name)
    # Remove trailing "-model"
    name = re.sub(r'[-_.]model$', '', name)
    return name.strip('-_.')


def _mmproj_compatible(model_filename: str, mmproj_filename: str) -> bool:
    """Heuristic: check if an mmproj file is compatible with a model.

    Compatibility is determined by comparing the stripped base names:
    one must begin with the other (case-insensitive).
    If either base name is empty (can't determine), we allow it.
    """
    model_base = _model_base_name(model_filename)
    mmproj_base = _model_base_name(mmproj_filename)
    if not model_base or not mmproj_base:
        return True
    # Allow if one is a prefix of the other
    return model_base.startswith(mmproj_base) or mmproj_base.startswith(model_base)


# llama-server binary location
LLAMACPP_SERVER_DIR = BASE_DIR / "llamacpp-server" / "bin"
if sys.platform == "win32":
    LLAMACPP_SERVER_BIN = LLAMACPP_SERVER_DIR / "llama-server.exe"
else:
    LLAMACPP_SERVER_BIN = LLAMACPP_SERVER_DIR / "llama-server"

# Port for the llama-server subprocess
LLAMACPP_BASE_PORT = 8281
LLAMACPP_HOST = "127.0.0.1"


def _kill_orphan_llama_servers():
    """Kill any llama-server processes left over from previous backend sessions."""
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if "llama-server" in name or "llama_server" in name:
                    log.info(f"Killing orphan llama-server PID={proc.pid}")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        # psutil not available — fall back to Windows taskkill
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "llama-server.exe"],
                    capture_output=True,
                    check=False,
                )
            except Exception:
                pass


_kill_orphan_llama_servers()

# HTTP client per model (keyed by port)
_http_clients: dict[int, "httpx.AsyncClient"] = {}


def _get_http_client(port: int) -> "httpx.AsyncClient":
    """Get or create an HTTP client for the given port."""
    global _http_clients
    if port not in _http_clients or _http_clients[port].is_closed:
        base_url = f"http://{LLAMACPP_HOST}:{port}"
        _http_clients[port] = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(300.0, connect=10.0),
        )
    return _http_clients[port]


def _strip_image_content(messages: list[dict]) -> list[dict]:
    """Remove image_url parts from multipart content messages.

    When a model has no mmproj (no vision capability), llama-server returns
    a 500 error if the request contains image_url content parts.  This helper
    converts multipart content back to a plain text string, stripping any
    image_url entries and similar non-text parts.
    """
    cleaned = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            cleaned.append({**msg, "content": "\n".join(text_parts).strip() or ""})
        else:
            cleaned.append(msg)
    return cleaned


def _messages_have_images(messages: list[dict]) -> bool:
    """Return True when any message includes image_url multipart content."""
    for msg in messages or []:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def _resolve_image_url(url: str) -> Optional[str]:
    """Resolve an image URL to a valid data URI for llama-server.

    If the URL is already a data URI, return as-is.
    If it's a file ID (not a URL), try to resolve it from storage.
    If it's an HTTP URL, download and convert.
    Returns None on failure.
    """
    if not url:
        return None

    # Already a valid data URI
    if url.startswith("data:image/"):
        return url

    # HTTP/HTTPS URL — download and convert
    if url.startswith("http://") or url.startswith("https://"):
        try:
            import requests as req_lib
            resp = req_lib.get(url, timeout=30)
            resp.raise_for_status()
            encoded = base64.b64encode(resp.content).decode("utf-8")
            ct = resp.headers.get("Content-Type", "image/png")
            return f"data:{ct};base64,{encoded}"
        except Exception as e:
            log.warning(f"_resolve_image_url: failed to download {url[:100]}: {e}")
            return None

    # Assume it's a file ID — try to resolve from Neve storage
    try:
        from neveai.models.files import Files
        from neveai.storage.provider import Storage

        file = Files.get_file_by_id(url)
        if not file:
            log.warning(f"_resolve_image_url: file not found for ID '{url[:60]}'")
            return None

        file_path = Storage.get_file(file.path)
        file_path = Path(file_path)
        if not file_path.is_file():
            log.warning(f"_resolve_image_url: file path does not exist: {file_path}")
            return None

        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        ct, _ = mimetypes.guess_type(file_path.name)
        if not ct:
            ct = "image/png"
        return f"data:{ct};base64,{encoded}"

    except Exception as e:
        log.warning(f"_resolve_image_url: failed to resolve file ID '{url[:60]}': {e}")
        return None


def _prepare_vision_messages(messages: list[dict]) -> list[dict]:
    """Validate and fix image_url content parts for llama-server.

    Ensures all image_url parts have valid data URIs.  Parts with invalid
    or unresolvable URLs are dropped with a warning.  If middleware already
    converted everything, this is a cheap no-op validation pass.
    """
    prepared = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            prepared.append(msg)
            continue

        new_parts = []
        for part in content:
            if not isinstance(part, dict):
                new_parts.append(part)
                continue

            if part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url")
                if not url or url == "None":
                    log.warning("_prepare_vision_messages: skipping image_url with no URL")
                    continue

                if not url.startswith("data:image/"):
                    log.info(f"_prepare_vision_messages: resolving non-data-URI image: {url[:80]}...")
                    resolved = _resolve_image_url(url)
                    if not resolved:
                        log.warning(f"_prepare_vision_messages: dropping unresolvable image_url: {url[:80]}")
                        continue
                    new_parts.append({
                        "type": "image_url",
                        "image_url": {"url": resolved},
                    })
                else:
                    new_parts.append(part)
            else:
                new_parts.append(part)

        # If all image parts were dropped, convert back to plain text
        has_images = any(
            isinstance(p, dict) and p.get("type") == "image_url"
            for p in new_parts
        )
        if not has_images:
            text_parts = [
                p.get("text", "")
                for p in new_parts
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            prepared.append({**msg, "content": "\n".join(text_parts).strip() or ""})
        else:
            prepared.append({**msg, "content": new_parts})

    return prepared


# ---------------------------------------------------------------------------
# Model Manager — manages llama-server subprocess
# ---------------------------------------------------------------------------

class _LoadedModelInfo:
    """Tracks information about the currently loaded model."""
    __slots__ = ("model_id", "filename", "loaded_at", "n_gpu_layers", "n_ctx", "file_size", "mmproj_filename")

    def __init__(self, model_id: str, filename: str, n_gpu_layers: int, n_ctx: int, file_size: int, mmproj_filename: Optional[str] = None):
        self.model_id = model_id
        self.filename = filename
        self.loaded_at = int(time.time())
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.file_size = file_size
        self.mmproj_filename = mmproj_filename


class LocalModelManager:
    """Manages multiple llama-server subprocesses (one per loaded model)."""

    def __init__(self):
        # model_id -> _LoadedModelInfo
        self._loaded: dict[str, _LoadedModelInfo] = {}
        # model_id -> subprocess.Popen
        self._processes: dict[str, subprocess.Popen] = {}
        # model_id -> port
        self._ports: dict[str, int] = {}
        self._lock = asyncio.Lock()

    # -- scanning --------------------------------------------------------

    def _next_free_port(self) -> int:
        """Find the next available port starting from LLAMACPP_BASE_PORT."""
        import socket
        used = set(self._ports.values())
        port = LLAMACPP_BASE_PORT
        while True:
            if port not in used:
                # Also verify the port is not in use by any external process
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        s.bind((LLAMACPP_HOST, port))
                        return port  # Successfully bound = port is free
                    except OSError:
                        pass  # Port in use, try next
            port += 1

    def scan_models(self) -> list[dict]:
        """Return list of .gguf files found in MODELS_DIR."""
        # Clean up stale entries first so scan reflects accurate state
        self._cleanup_stale()

        results = []
        if not MODELS_DIR.exists():
            return results

        for f in sorted(MODELS_DIR.iterdir()):
            if f.suffix.lower() == ".gguf" and f.is_file():
                model_id = f"local/{f.stem}"
                file_size = f.stat().st_size
                is_loaded = model_id in self._loaded and self._is_process_alive(model_id)
                info = self._loaded.get(model_id)
                results.append({
                    "id": model_id,
                    "filename": f.name,
                    "file_size": file_size,
                    "file_size_human": _human_size(file_size),
                    "is_loaded": is_loaded,
                    "loaded_at": info.loaded_at if is_loaded else None,
                    "n_gpu_layers": info.n_gpu_layers if is_loaded else None,
                    "n_ctx": info.n_ctx if is_loaded else None,
                    "mmproj_filename": info.mmproj_filename if is_loaded else None,
                })
        return results

    def scan_mmproj_files(self) -> list[str]:
        """Return list of .gguf files found in MMPROJ_DIR (vision encoder files)."""
        results = []
        if not MMPROJ_DIR.exists():
            return results
        for f in sorted(MMPROJ_DIR.iterdir()):
            # Accept .gguf files inside mmproj/ folder
            if f.suffix.lower() in (".gguf", ".mmproj") and f.is_file():
                results.append(f.name)
        return results

    def get_loaded_models(self) -> list[dict]:
        """Return models that are currently loaded in memory."""
        return [m for m in self.scan_models() if m["is_loaded"]]

    def auto_detect_mmproj(self, model_filename: str) -> Optional[str]:
        """Auto-detect a compatible mmproj file for the given model."""
        mmproj_files = self.scan_mmproj_files()
        for mmproj_file in mmproj_files:
            if _mmproj_compatible(model_filename, mmproj_file):
                log.info(f"Auto-detected compatible mmproj: {mmproj_file} for model {model_filename}")
                return mmproj_file
        return None

    def _is_process_alive(self, model_id: str) -> bool:
        proc = self._processes.get(model_id)
        return proc is not None and proc.poll() is None

    def _cleanup_stale(self):
        """Remove entries from _loaded/_processes/_ports where the process is no longer alive.

        This prevents state desynchronization where the manager thinks a model is loaded
        but the underlying llama-server process has died or was killed externally.
        """
        stale_ids = []
        for model_id in list(self._loaded.keys()):
            if not self._is_process_alive(model_id):
                stale_ids.append(model_id)

        for model_id in stale_ids:
            log.warning(f"_cleanup_stale: removing dead model entry '{model_id}' (process no longer alive)")
            self._loaded.pop(model_id, None)
            proc = self._processes.pop(model_id, None)
            port = self._ports.pop(model_id, None)
            # Close stale HTTP client
            if port and port in _http_clients:
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(_http_clients[port].aclose())
                    else:
                        loop.run_until_complete(_http_clients[port].aclose())
                except Exception:
                    pass
                _http_clients.pop(port, None)
            # Try to kill the zombie process if it somehow has a Popen object
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass

        if stale_ids:
            log.info(f"_cleanup_stale: cleaned up {len(stale_ids)} stale model entries: {stale_ids}")

    # -- loading / unloading --------------------------------------------

    async def load_model(
        self,
        filename: str,
        n_gpu_layers: int = -1,
        n_ctx: int = 4096,
        mmproj_filename: Optional[str] = None,
        cache_type: str = "q8_0",
    ) -> dict:
        """Load a .gguf model by starting a new llama-server subprocess."""
        # Clean up stale entries before loading to prevent phantom models
        self._cleanup_stale()

        filepath = MODELS_DIR / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Model file not found: {filename}")
        if not filepath.suffix.lower() == ".gguf":
            raise ValueError("Only .gguf files are supported")

        # Auto-detect mmproj if not explicitly provided (None = not specified; empty string = explicitly no mmproj)
        if mmproj_filename is None:
            mmproj_filename = self.auto_detect_mmproj(filename)

        mmproj_path: Optional[Path] = None
        if mmproj_filename:
            mmproj_path = MMPROJ_DIR / mmproj_filename
            if not mmproj_path.exists():
                # Fallback: also check models/ dir for backwards compatibility
                fallback = MODELS_DIR / mmproj_filename
                if fallback.exists():
                    mmproj_path = fallback
                else:
                    raise FileNotFoundError(f"mmproj file not found: {mmproj_filename}")

        model_id = f"local/{filepath.stem}"

        async with self._lock:
            # Unload ALL currently loaded models before loading a new one
            # This ensures only one model is active at a time and frees file handles
            other_ids = [mid for mid in list(self._loaded.keys()) if mid != model_id]
            for other_id in other_ids:
                log.info(f"Auto-unloading model {other_id} before loading {model_id}")
                await self._kill_server(other_id)
                self._loaded.pop(other_id, None)

            # If this exact model is already loaded, unload it first (reload scenario)
            if model_id in self._loaded:
                await self._kill_server(model_id)

            # Assign a free port
            port = self._next_free_port()
            self._ports[model_id] = port

            # Start new llama-server with the model on this port
            await self._start_server(filepath, n_gpu_layers, n_ctx, mmproj_path, port, model_id, cache_type)

            file_size = filepath.stat().st_size
            self._loaded[model_id] = _LoadedModelInfo(model_id, filename, n_gpu_layers, n_ctx, file_size, mmproj_filename)

            log.info(f"Model loaded via llama-server: {model_id} (port={port}, gpu_layers={n_gpu_layers}, ctx={n_ctx}, mmproj={mmproj_filename})")
            return {
                "id": model_id,
                "filename": filename,
                "status": "loaded",
                "n_gpu_layers": n_gpu_layers,
                "n_ctx": n_ctx,
                "mmproj_filename": mmproj_filename,
            }

    async def unload_model(self, model_id: str) -> dict:
        """Unload a model by stopping its llama-server."""
        async with self._lock:
            if model_id not in self._loaded:
                raise KeyError(f"Model not loaded: {model_id}")

            await self._kill_server(model_id)
            del self._loaded[model_id]
            log.info(f"Model unloaded: {model_id}")
            return {"id": model_id, "status": "unloaded"}

    def is_model_loaded(self, model_id: str) -> bool:
        """Check if a specific model is loaded and its process is alive."""
        if model_id in self._loaded:
            if self._is_process_alive(model_id):
                return True
            else:
                # Process died — clean up stale entry
                log.warning(f"is_model_loaded: model '{model_id}' was in _loaded but process is dead, cleaning up")
                self._loaded.pop(model_id, None)
                self._processes.pop(model_id, None)
                port = self._ports.pop(model_id, None)
                if port and port in _http_clients:
                    _http_clients.pop(port, None)
        return False

    def get_loaded_model_id(self) -> Optional[str]:
        """Get the ID of the first loaded model (for backward compat), or None."""
        for model_id in self._loaded:
            if self._is_process_alive(model_id):
                return model_id
        return None

    # -- standby / resume (VRAM management) -----------------------------

    async def standby(self) -> Optional[dict]:
        """Unload ALL loaded models and return info needed to resume them later.

        Returns None if no models were loaded. Returns a dict with the model
        info needed by resume() to reload the models.
        """
        self._cleanup_stale()

        if not self._loaded:
            return None

        # Collect info before unloading
        standby_info = []
        for model_id, info in list(self._loaded.items()):
            standby_info.append({
                "filename": info.filename,
                "n_gpu_layers": info.n_gpu_layers,
                "n_ctx": info.n_ctx,
                "mmproj_filename": info.mmproj_filename,
            })

        # Unload all models
        for model_id in list(self._loaded.keys()):
            try:
                await self.unload_model(model_id)
            except Exception as e:
                log.warning(f"standby: failed to unload {model_id}: {e}")

        log.info(f"LLM standby: unloaded {len(standby_info)} model(s)")
        return {"models": standby_info}

    async def resume(self, standby_info: dict):
        """Reload models that were previously put in standby."""
        models = standby_info.get("models", [])
        if not models:
            return

        log.info(f"LLM resume: reloading {len(models)} model(s)")
        for m in models:
            try:
                # Read cache_type from localStorage default
                cache_type = "q8_0"
                await self.load_model(
                    filename=m["filename"],
                    n_gpu_layers=m["n_gpu_layers"],
                    n_ctx=m["n_ctx"],
                    mmproj_filename=m.get("mmproj_filename"),
                    cache_type=cache_type,
                )
            except Exception as e:
                log.error(f"resume: failed to reload {m['filename']}: {e}")

    # -- subprocess management ------------------------------------------

    async def _start_server(self, model_path: Path, n_gpu_layers: int, n_ctx: int, mmproj_path: Optional[Path], port: int, model_id: str, cache_type: str = "q8_0"):
        """Start llama-server.exe with the given model on the given port."""
        if not LLAMACPP_SERVER_BIN.exists():
            raise FileNotFoundError(
                f"llama-server binary not found at: {LLAMACPP_SERVER_BIN}\n"
                "Please download from https://github.com/ggml-org/llama.cpp/releases"
            )

        cmd = [
            str(LLAMACPP_SERVER_BIN),
            "--model", str(model_path),
            "--host", LLAMACPP_HOST,
            "--port", str(port),
            "--n-gpu-layers", str(n_gpu_layers),
            "--ctx-size", str(n_ctx),
            "--flash-attn", "auto",
            "--cache-type-k", cache_type,
            "--cache-type-v", cache_type,
            "--no-webui",
        ]

        # Speculative decoding (n-gram, zero VRAM cost) — disabled for vision models
        # because multimodal prefill breaks the n-gram locality assumption.
        if mmproj_path is None:
            cmd += [
                "--spec-type", "ngram-mod",
                "--spec-ngram-size-n", "24",
                "--draft-min", "48",
                "--draft-max", "64",
            ]

        if mmproj_path is not None:
            cmd += ["--mmproj", str(mmproj_path)]

        log.info(f"Starting llama-server on port {port}: {' '.join(cmd)}")

        # Set up environment with DLL paths
        env = os.environ.copy()
        env["PATH"] = str(LLAMACPP_SERVER_DIR) + os.pathsep + env.get("PATH", "")

        # Start subprocess
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=creation_flags,
            cwd=str(LLAMACPP_SERVER_DIR),
        )
        self._processes[model_id] = proc

        # Wait for server to be ready
        await self._wait_for_server(port, model_id, timeout=120)

    async def _wait_for_server(self, port: int, model_id: str, timeout: int = 120):
        """Wait for llama-server to be ready (health check)."""
        client = _get_http_client(port)
        deadline = time.time() + timeout
        last_error = None

        while time.time() < deadline:
            proc = self._processes.get(model_id)
            # Check if process died
            if proc and proc.poll() is not None:
                stderr = ""
                try:
                    stderr = proc.stderr.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                # Clean up
                self._processes.pop(model_id, None)
                self._ports.pop(model_id, None)
                raise RuntimeError(
                    f"llama-server exited with code {proc.returncode}.\n"
                    f"Stderr: {stderr[-2000:]}"
                )

            try:
                resp = await client.get("/health")
                data = resp.json()
                status = data.get("status", "")
                if resp.status_code == 200 and status == "ok":
                    log.info(f"llama-server on port {port} is ready!")
                    return
                elif status == "loading model":
                    log.debug(f"llama-server port {port}: loading model...")
            except (httpx.ConnectError, httpx.ConnectTimeout):
                pass
            except Exception as e:
                last_error = e

            await asyncio.sleep(1)

        # Timeout — clean up
        await self._kill_server(model_id)
        raise TimeoutError(
            f"llama-server on port {port} did not become ready within {timeout}s. "
            f"Last error: {last_error}"
        )

    async def _kill_server(self, model_id: str):
        """Kill the llama-server subprocess for a specific model."""
        proc = self._processes.pop(model_id, None)
        port = self._ports.pop(model_id, None)

        # Close and remove the HTTP client for this port
        if port and port in _http_clients:
            try:
                await _http_clients[port].aclose()
            except Exception:
                pass
            del _http_clients[port]

        if proc is not None:
            try:
                if proc.poll() is None:
                    log.info(f"_kill_server: killing llama-server for {model_id} (pid={proc.pid})")
                    if sys.platform == "win32":
                        # Use taskkill /F /T to kill the entire process tree on Windows
                        # This ensures child processes are also killed and file handles released
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                capture_output=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                        except Exception:
                            proc.kill()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                    else:
                        proc.send_signal(signal.SIGTERM)
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    # Wait a moment for the OS to release file handles and port
                    await asyncio.sleep(1.5)
                    log.info(f"llama-server process for {model_id} terminated (pid={proc.pid})")
                else:
                    log.info(f"_kill_server: process for {model_id} already dead (pid={proc.pid}, rc={proc.returncode})")
            except Exception as e:
                log.warning(f"Error killing llama-server for {model_id}: {e}")

        # Extra safety: verify the port is actually free now
        if port is not None:
            import socket
            for attempt in range(3):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s.bind((LLAMACPP_HOST, port))
                        log.debug(f"_kill_server: port {port} confirmed free after killing {model_id}")
                        break
                except OSError:
                    log.warning(f"_kill_server: port {port} still in use after killing {model_id}, waiting... (attempt {attempt+1}/3)")
                    await asyncio.sleep(1)
            else:
                log.error(f"_kill_server: port {port} still in use after 3 attempts for {model_id}")

    # -- chat completion (proxy to llama-server) -------------------------

    async def chat_completion(
        self,
        model_id: str,
        messages: list[dict],
        stream: bool = False,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 0,
        min_p: float = 0.0,
        max_tokens: int = -1,
        stop: Optional[list[str]] = None,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        repeat_penalty: float = 1.0,
        seed: Optional[int] = None,
        mirostat: int = 0,
        mirostat_eta: float = 0.1,
        mirostat_tau: float = 5.0,
        xtc_threshold: Optional[float] = None,
        xtc_probability: Optional[float] = None,
        dry_multiplier: Optional[float] = None,
        dry_allowed_length: Optional[int] = None,
        dry_base: Optional[float] = None,
        no_think: bool = False,
    ):
        """Proxy a chat completion request to llama-server for the given model."""
        if not self.is_model_loaded(model_id):
            raise KeyError(f"Model not loaded: {model_id}")

        # Verify the llama-server is actually responsive before sending completion request
        port = self._ports.get(model_id)
        if port is None:
            log.error(f"chat_completion: no port assigned for model '{model_id}', cleaning up")
            self._loaded.pop(model_id, None)
            self._processes.pop(model_id, None)
            raise KeyError(f"Model not loaded (no port): {model_id}")

        client = _get_http_client(port)
        try:
            health_resp = await client.get("/health", timeout=5.0)
            if health_resp.status_code != 200:
                health_data = health_resp.json() if health_resp.headers.get("content-type", "").startswith("application/json") else {}
                health_status = health_data.get("status", "unknown")
                log.warning(f"chat_completion: llama-server health check failed for {model_id}: status={health_status}, http={health_resp.status_code}")
                if health_status == "loading model":
                    raise RuntimeError(f"Model '{model_id}' is still loading, please wait...")
                # Server not healthy — clean up and raise
                log.error(f"chat_completion: removing unhealthy model '{model_id}'")
                self._loaded.pop(model_id, None)
                self._processes.pop(model_id, None)
                self._ports.pop(model_id, None)
                raise KeyError(f"Model not loaded (server unhealthy): {model_id}")
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            log.error(f"chat_completion: cannot connect to llama-server for {model_id} on port {port}: {e}")
            self._loaded.pop(model_id, None)
            self._processes.pop(model_id, None)
            self._ports.pop(model_id, None)
            raise KeyError(f"Model not loaded (connection failed): {model_id}")

        # Sanitize messages based on vision capability
        info = self._loaded.get(model_id)
        has_vision = info and info.mmproj_filename
        if has_vision:
            # Model has mmproj — validate and fix image content for llama-server
            log.info(f"chat_completion: model {model_id} has vision (mmproj={info.mmproj_filename})")
            messages = _prepare_vision_messages(messages)
        else:
            # No vision — strip all image content
            messages = _strip_image_content(messages)

        # Log message content structure for debugging (without full base64 data)
        for i, msg in enumerate(messages):
            content = msg.get("content")
            if isinstance(content, list):
                parts_summary = []
                for p in content:
                    if isinstance(p, dict):
                        ptype = p.get("type", "?")
                        if ptype == "image_url":
                            url = (p.get("image_url") or {}).get("url", "")
                            url_preview = (url[:60] + "...") if url and len(url) > 60 else url
                            parts_summary.append(f"image_url({url_preview})")
                        else:
                            parts_summary.append(ptype)
                log.debug(f"  msg[{i}] role={msg.get('role')} content_parts={parts_summary}")

        # port and client already obtained above during health check

        payload = {
            "model": model_id,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        }
        if stop:
            payload["stop"] = stop
        if top_k and top_k > 0:
            payload["top_k"] = top_k
        if min_p and min_p > 0:
            payload["min_p"] = min_p
        if repeat_penalty != 1.0:
            payload["repeat_penalty"] = repeat_penalty
        if seed is not None:
            payload["seed"] = seed
        if mirostat and mirostat > 0:
            payload["mirostat"] = mirostat
            payload["mirostat_eta"] = mirostat_eta
            payload["mirostat_tau"] = mirostat_tau
        if xtc_threshold is not None:
            payload["xtc_threshold"] = xtc_threshold
        if xtc_probability is not None:
            payload["xtc_probability"] = xtc_probability
        if dry_multiplier is not None:
            payload["dry_multiplier"] = dry_multiplier
        if dry_allowed_length is not None:
            payload["dry_allowed_length"] = dry_allowed_length
        if dry_base is not None:
            payload["dry_base"] = dry_base

        # Disable reasoning/thinking when requested
        if no_think:
            # chat_template_kwargs passes enable_thinking=false to the Jinja template
            # This works for Qwen3, Gemma and other models with thinking support
            payload["chat_template_kwargs"] = {"enable_thinking": False}
            # reasoning_format=none prevents parsing/extracting <think> tags
            payload["reasoning_format"] = "none"

        if stream:
            return self._stream_proxy(client, payload, model_id)
        else:
            resp = await client.post("/v1/chat/completions", json=payload, timeout=300.0)
            if resp.status_code != 200:
                log.error(f"llama-server non-stream error {resp.status_code}: {resp.text[:1000]}")
                raise RuntimeError(f"llama-server error: {resp.status_code} - {resp.text}")
            result = resp.json()
            # Override model name to our model_id
            result["model"] = model_id
            return result

    def _stream_proxy(self, client: httpx.AsyncClient, payload: dict, model_id: str):
        """Stream SSE from llama-server back to the client."""
        async def _generate():
            try:
                async with client.stream(
                    "POST",
                    "/v1/chat/completions",
                    json=payload,
                    timeout=300.0,
                ) as resp:
                    if resp.status_code != 200:
                        text = await resp.aread()
                        error_text = text.decode("utf-8", errors="replace")[:500]
                        log.error(f"llama-server stream error {resp.status_code}: {error_text}")
                        error_data = {
                            "id": f"chatcmpl-error-{int(time.time())}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": model_id,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": f"\n\n[Server Error {resp.status_code}: {error_text}]"},
                                "finish_reason": "stop",
                            }],
                        }
                        yield f"data: {json.dumps(error_data)}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                yield "data: [DONE]\n\n"
                                break
                            try:
                                data = json.loads(data_str)
                                data["model"] = model_id
                                yield f"data: {json.dumps(data)}\n\n"
                            except json.JSONDecodeError:
                                yield f"{line}\n\n"
            except Exception as e:
                log.error(f"Stream proxy error: {e}")
                error_data = {
                    "id": f"chatcmpl-error-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_id,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"\n\n[Error: {str(e)}]"},
                        "finish_reason": "stop",
                    }],
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                yield "data: [DONE]\n\n"

        return _generate()


# Singleton
model_manager = LocalModelManager()


# ---------------------------------------------------------------------------
# Pydantic models for API
# ---------------------------------------------------------------------------

class LoadModelRequest(BaseModel):
    filename: str
    n_gpu_layers: int = -1  # -1 = all layers on GPU
    n_ctx: int = 4096
    mmproj_filename: Optional[str] = None
    cache_type: str = "q8_0"  # q4_0 | q8_0 | f16

class UnloadModelRequest(BaseModel):
    model_id: str


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_local_models():
    """List all .gguf models found in the models/ directory."""
    models = model_manager.scan_models()
    return {"models": models}


@router.get("/models/mmproj")
async def list_mmproj_files():
    """List all .mmproj files found in the models/ directory."""
    files = model_manager.scan_mmproj_files()
    return {"mmproj_files": files}


@router.get("/models/loaded")
async def list_loaded_models():
    """List only the currently loaded models."""
    models = model_manager.get_loaded_models()
    return {"models": models}


@router.post("/models/load")
async def load_model(req: LoadModelRequest, request: Request):
    """Load a .gguf model by starting llama-server with it."""
    try:
        result = await model_manager.load_model(
            filename=req.filename,
            n_gpu_layers=req.n_gpu_layers,
            n_ctx=req.n_ctx,
            mmproj_filename=req.mmproj_filename,
            cache_type=req.cache_type,
        )
        # Invalidate cached base models so /api/models returns fresh n_ctx
        request.app.state.BASE_MODELS = None
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (TimeoutError, RuntimeError) as e:
        log.error(f"Error loading model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        log.error(f"Error loading model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/unload")
async def unload_model(req: UnloadModelRequest, request: Request):
    """Unload a model (stop llama-server)."""
    try:
        result = await model_manager.unload_model(req.model_id)
        # Invalidate cached base models
        request.app.state.BASE_MODELS = None
        return result
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"Error unloading model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/completions")
async def local_chat_completion(request: Request):
    """
    OpenAI-compatible chat completion endpoint for local GGUF models.
    """
    body = await request.json()

    model_id = body.get("model", "")
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    temperature = body.get("temperature", 0.7)
    top_p = body.get("top_p", 0.9)
    max_tokens = body.get("max_tokens", -1)  # -1 = unlimited (bounded by n_ctx)
    stop = body.get("stop", None)
    frequency_penalty = body.get("frequency_penalty", 0.0)
    presence_penalty = body.get("presence_penalty", 0.0)

    if not model_id.startswith("local/"):
        raise HTTPException(status_code=400, detail="Model ID must start with 'local/'")

    if not model_manager.is_model_loaded(model_id):
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model_id}' is not loaded. Load it first via POST /llamacpp/models/load",
        )

    try:
        if stream:
            generator = await model_manager.chat_completion(
                model_id=model_id,
                messages=messages,
                stream=True,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stop=stop,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
            )
            return StreamingResponse(
                generator,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            result = await model_manager.chat_completion(
                model_id=model_id,
                messages=messages,
                stream=False,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stop=stop,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
            )
            return result
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Functions used by the model integration layer
# ---------------------------------------------------------------------------

async def get_all_models(request=None, user=None) -> dict:
    """
    Return all local GGUF models (loaded or not) in a format compatible with
    get_all_base_models(). Models will be auto-loaded when selected for chat.
    """
    all_models = model_manager.scan_models()
    return {
        "models": [
            {
                "id": m["id"],
                "name": m["filename"].replace(".gguf", "").replace("-", " ").replace("_", " ").title(),
                "object": "model",
                "created": m["loaded_at"] or int(time.time()),
                "owned_by": "llamacpp",
                "connection_type": "local",
                "llamacpp": {
                    "filename": m["filename"],
                    "file_size": m["file_size"],
                    "file_size_human": m["file_size_human"],
                    "n_gpu_layers": m["n_gpu_layers"],
                    "n_ctx": m["n_ctx"],
                    "is_loaded": m["is_loaded"],
                },
            }
            for m in all_models
        ]
    }


async def generate_chat_completion(
    request: Request,
    form_data: dict,
    user=None,
    bypass_filter: bool = False,
    bypass_system_prompt: bool = False,
):
    """
    Generate a chat completion for a local GGUF model.
    Called from utils/chat.py when owned_by == "llamacpp".
    """
    model_id = form_data.get("model", "")
    messages = form_data.get("messages", [])
    log.info(f"generate_chat_completion: requested model_id='{model_id}'")

    # Apply model system prompt and params from Model Editor (same as ollama/openai routers)
    metadata = form_data.pop("metadata", {})
    model_info = Models.get_model_by_id(model_id)

    # Resolve custom model IDs to their base model ID (local/<stem>).
    # Custom models created in the workspace have their own ID (e.g. "my-model") but
    # reference the actual GGUF via base_model_id = "local/<stem>".  Without this
    # resolution the scan below would fail to find the file.
    if model_info and model_info.base_model_id and model_info.base_model_id.startswith("local/"):
        log.info(
            f"generate_chat_completion: resolving custom model '{model_id}' "
            f"→ base_model_id '{model_info.base_model_id}'"
        )
        model_id = model_info.base_model_id
    elif model_info:
        log.info(f"generate_chat_completion: model_info found, base_model_id='{model_info.base_model_id}', no resolution needed")
    else:
        log.info(f"generate_chat_completion: no model_info found for '{model_id}', using as-is")

    if model_info:
        params = model_info.params.model_dump()
        if params:
            system = params.pop("system", None)
            form_data = apply_model_params_to_body_openai(params, form_data)
            if not bypass_system_prompt:
                form_data = apply_system_prompt_to_body(system, form_data, metadata, user)
            # Re-read messages after system prompt injection
            messages = form_data.get("messages", messages)

    # --- Thinking/Reasoning toggle ---
    no_think = form_data.pop("no_think", False)

    stream = form_data.get("stream", False)
    temperature = form_data.get("temperature", 0.7)
    top_p = form_data.get("top_p", 0.9)
    top_k = form_data.get("top_k", 0)
    min_p = form_data.get("min_p", 0.0)
    max_tokens = form_data.get("max_tokens", -1)  # -1 = unlimited (bounded by n_ctx)
    stop = form_data.get("stop", None)
    frequency_penalty = form_data.get("frequency_penalty", 0.0)
    presence_penalty = form_data.get("presence_penalty", 0.0)
    repeat_penalty = form_data.get("repeat_penalty", 1.0)
    seed = form_data.get("seed", None)
    mirostat = form_data.get("mirostat", 0)
    mirostat_eta = form_data.get("mirostat_eta", 0.1)
    mirostat_tau = form_data.get("mirostat_tau", 5.0)
    xtc_threshold = form_data.get("xtc_threshold", None)
    xtc_probability = form_data.get("xtc_probability", None)
    dry_multiplier = form_data.get("dry_multiplier", None)
    dry_allowed_length = form_data.get("dry_allowed_length", None)
    dry_base = form_data.get("dry_base", None)

    model_filename = None
    for m in model_manager.scan_models():
        if m["id"] == model_id:
            model_filename = m["filename"]
            break

    if not model_filename:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found in models directory.",
        )

    has_image_input = _messages_have_images(messages)

    if not model_manager.is_model_loaded(model_id):
        # Model is NOT loaded — return an error so the frontend can ask the user.
        currently_loaded = list(model_manager._loaded.keys())
        log.warning(
            f"generate_chat_completion: model '{model_id}' is NOT loaded. "
            f"Currently loaded: {currently_loaded}. Returning 409."
        )
        raise HTTPException(
            status_code=409,
            detail=f"Model '{model_id}' is not loaded. Please load it first via the model selector.",
        )
    else:
        loaded_info = model_manager._loaded.get(model_id)
        if has_image_input and loaded_info and not loaded_info.mmproj_filename:
            mmproj = model_manager.auto_detect_mmproj(model_filename)
            if mmproj:
                log.info(
                    f"Reloading model {model_id} with mmproj={mmproj} due to image input"
                )
                try:
                    await model_manager.load_model(
                        filename=model_filename,
                        n_gpu_layers=loaded_info.n_gpu_layers,
                        n_ctx=loaded_info.n_ctx,
                        mmproj_filename=mmproj,
                    )
                except Exception as e:
                    log.error(
                        f"Failed to reload model {model_id} with mmproj={mmproj}: {e}"
                    )

    # When thinking is disabled, inject /no_think into last user message
    if no_think:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                content = messages[i].get("content", "")
                if isinstance(content, str) and not content.startswith("/no_think"):
                    messages[i]["content"] = "/no_think " + content
                elif isinstance(content, list):
                    for part in content:
                        if part.get("type") == "text" and not part["text"].startswith("/no_think"):
                            part["text"] = "/no_think " + part["text"]
                            break
                break
        log.info(f"generate_chat_completion: thinking disabled for model {model_id}")

    if stream:
        generator = await model_manager.chat_completion(
            model_id=model_id,
            messages=messages,
            stream=True,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            stop=stop,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            repeat_penalty=repeat_penalty,
            seed=seed,
            mirostat=mirostat,
            mirostat_eta=mirostat_eta,
            mirostat_tau=mirostat_tau,
            xtc_threshold=xtc_threshold,
            xtc_probability=xtc_probability,
            dry_multiplier=dry_multiplier,
            dry_allowed_length=dry_allowed_length,
            dry_base=dry_base,
            no_think=no_think,
        )
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = await model_manager.chat_completion(
            model_id=model_id,
            messages=messages,
            stream=False,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            max_tokens=max_tokens,
            stop=stop,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            repeat_penalty=repeat_penalty,
            seed=seed,
            mirostat=mirostat,
            mirostat_eta=mirostat_eta,
            mirostat_tau=mirostat_tau,
            xtc_threshold=xtc_threshold,
            xtc_probability=xtc_probability,
            dry_multiplier=dry_multiplier,
            dry_allowed_length=dry_allowed_length,
            dry_base=dry_base,
            no_think=no_think,
        )
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_size(nbytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


# ---------------------------------------------------------------------------
# Hugging Face download — Neve catalog
# ---------------------------------------------------------------------------

import uuid
import threading

NEVE_CATALOG = [
    {"id": "neve-echo-s",   "name": "Neve Echo S",   "repo": "NeveAI/Neve-Echo-S-4B-GGUF",    "size_label": "7.9 GB"},
    {"id": "neve-echo",     "name": "Neve Echo",     "repo": "NeveAI/Neve-Echo-4-26B-GGUF",   "size_label": "13.6 GB"},
    {"id": "neve-prism",    "name": "Neve Prism",    "repo": "NeveAI/Neve-Prism-3-12B-GGUF",  "size_label": "8.1 GB"},
    {"id": "neve-prism-x",  "name": "Neve Prism X",  "repo": "NeveAI/Neve-Prism-X2-9B-GGUF",  "size_label": "12.1 GB"},
    {"id": "neve-sense",    "name": "Neve Sense",    "repo": "NeveAI/Neve-Sense-2-20B-GGUF",  "size_label": "11.1 GB"},
    {"id": "neve-strata-s", "name": "Neve Strata S", "repo": "NeveAI/Neve-Strata-S2-4B-GGUF", "size_label": "5.5 GB"},
    {"id": "neve-strata",   "name": "Neve Strata",   "repo": "NeveAI/Neve-Strata-4-30B-GGUF", "size_label": "16.3 GB"},
    {"id": "neve-strata-x", "name": "Neve Strata X", "repo": "NeveAI/Neve-Strata-X2-35B-GGUF", "size_label": "18.2 GB"},
]

# In-memory task registry: { task_id: { status, progress, total, downloaded, message, files: [...] } }
_DOWNLOAD_TASKS: dict = {}
_DOWNLOAD_TASKS_LOCK = threading.Lock()


def _set_task(task_id: str, **fields):
    with _DOWNLOAD_TASKS_LOCK:
        task = _DOWNLOAD_TASKS.setdefault(task_id, {})
        task.update(fields)


def _get_task(task_id: str) -> dict:
    with _DOWNLOAD_TASKS_LOCK:
        return dict(_DOWNLOAD_TASKS.get(task_id, {}))


def _catalog_entry(model_id: str) -> Optional[dict]:
    return next((m for m in NEVE_CATALOG if m["id"] == model_id), None)


def _local_filename_for(repo_filename: str, repo_id: str) -> str:
    """Produce a stable local filename to avoid collisions between repos."""
    return repo_filename


def _is_installed(repo_filename: str) -> bool:
    return (MODELS_DIR / repo_filename).exists()


async def _hf_list_files(repo_id: str) -> list[dict]:
    """Return file listing of a HF repo (main branch). Each item: {path, size}."""
    url = f"https://huggingface.co/api/models/{repo_id}/tree/main"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def _pick_main_gguf(files: list[dict]) -> Optional[dict]:
    """Pick the first non-mmproj .gguf file from a HF repo listing."""
    for f in files:
        path = f.get("path", "")
        if path.lower().endswith(".gguf") and "mmproj" not in path.lower():
            return f
    return None


def _pick_mmproj(files: list[dict]) -> Optional[dict]:
    for f in files:
        path = f.get("path", "")
        lower = path.lower()
        if lower.endswith(".gguf") and "mmproj" in lower:
            return f
    return None


async def _stream_download_file(
    task_id: str,
    repo_id: str,
    repo_path: str,
    dest_path: Path,
    file_index: int,
    file_total: int,
):
    """Stream a single file from HF to disk, updating task progress."""
    url = f"https://huggingface.co/{repo_id}/resolve/main/{repo_path}"
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            _set_task(
                task_id,
                status="downloading",
                current_file=repo_path,
                file_index=file_index,
                file_total=file_total,
                downloaded=0,
                total=total,
                progress=0.0,
            )
            with open(tmp_path, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress = (downloaded / total) if total > 0 else 0.0
                    _set_task(
                        task_id,
                        downloaded=downloaded,
                        total=total,
                        progress=progress,
                    )
    tmp_path.replace(dest_path)


async def _run_download_task(task_id: str, model_id: str):
    entry = _catalog_entry(model_id)
    if not entry:
        _set_task(task_id, status="error", error="Modelo não encontrado no catálogo")
        return
    repo_id = entry["repo"]
    try:
        _set_task(task_id, status="resolving", model_id=model_id, repo_id=repo_id, name=entry["name"])
        files = await _hf_list_files(repo_id)
        main_file = _pick_main_gguf(files)
        if not main_file:
            _set_task(task_id, status="error", error=f"Nenhum .gguf encontrado em {repo_id}")
            return
        mmproj_file = _pick_mmproj(files)

        targets: list[tuple[str, Path]] = []
        if not _is_installed(main_file["path"]):
            targets.append((main_file["path"], MODELS_DIR / main_file["path"]))
        if mmproj_file and not (MMPROJ_DIR / mmproj_file["path"]).exists():
            targets.append((mmproj_file["path"], MMPROJ_DIR / mmproj_file["path"]))

        if not targets:
            _set_task(task_id, status="completed", message="Já instalado", progress=1.0)
            return

        total_files = len(targets)
        for i, (repo_path, dest_path) in enumerate(targets, start=1):
            await _stream_download_file(task_id, repo_id, repo_path, dest_path, i, total_files)

        _set_task(task_id, status="completed", progress=1.0, message="Download concluído")
    except httpx.HTTPStatusError as e:
        _set_task(task_id, status="error", error=f"HTTP {e.response.status_code} ao baixar de {repo_id}")
    except Exception as e:
        log.exception(f"Erro no download do modelo {model_id}")
        _set_task(task_id, status="error", error=str(e))


@router.get("/catalog")
async def get_neve_catalog():
    """Return the curated Neve model catalog with installed status and fixed size label."""
    items = []
    for entry in NEVE_CATALOG:
        repo_short = entry["repo"].split("/")[-1].lower().replace("-gguf", "")
        installed = False
        try:
            for p in MODELS_DIR.glob("*.gguf"):
                if repo_short in p.name.lower():
                    installed = True
                    break
        except Exception:
            pass
        items.append({**entry, "installed": installed})
    return {"models": items}


class DownloadModelRequest(BaseModel):
    model_id: str


@router.post("/download")
async def start_download(req: DownloadModelRequest):
    """Start a background download of a Neve catalog model. Returns task_id."""
    if not _catalog_entry(req.model_id):
        raise HTTPException(status_code=404, detail="Modelo não encontrado no catálogo")
    task_id = uuid.uuid4().hex
    _set_task(task_id, status="queued", model_id=req.model_id, progress=0.0)
    asyncio.create_task(_run_download_task(task_id, req.model_id))
    return {"task_id": task_id}


@router.get("/download/status/{task_id}")
async def stream_download_status(task_id: str):
    """SSE stream of download progress for a given task."""
    if not _get_task(task_id):
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    async def event_gen():
        last_serialized = None
        while True:
            task = _get_task(task_id)
            payload = json.dumps(task)
            if payload != last_serialized:
                yield f"data: {payload}\n\n"
                last_serialized = payload
            status = task.get("status")
            if status in ("completed", "error"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
