"""Memory-aware local context planning using llama.cpp's allocation-free fitter."""

import logging
import math
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)
AUTO_CONTEXT_CAP = 32768


def bounded_context(value: int) -> int:
    if value <= 0:
        raise ValueError("The runtime did not report a valid context size")
    return 1 << (min(value, AUTO_CONTEXT_CAP).bit_length() - 1)


def context_memory_margin(mmproj_path: Path | None, prediction: bool) -> int:
    # Reserve memory for the desktop, projector buffers and the MTP draft context.
    margin = 2048
    if mmproj_path is not None:
        margin += math.ceil(mmproj_path.stat().st_size / (1024 * 1024)) + 512
    if prediction:
        margin += 1024
    return margin


def plan_auto_context(
    server_dir: Path, model_path: Path, gpu_layers: int, cache_type: str,
    mmproj_path: Path | None = None, prediction: bool = False, device: str | None = None,
    prioritize_gpu: bool = False,
) -> tuple[int, int]:
    binary = server_dir / ("llama-fit-params.exe" if sys.platform == "win32" else "llama-fit-params")
    if not binary.exists():
        return (AUTO_CONTEXT_CAP if prioritize_gpu else 0), gpu_layers
    margin = context_memory_margin(mmproj_path, prediction) - (1024 if prioritize_gpu else 0)
    cmd = [str(binary), "--model", str(model_path), "--ctx-size", "0",
           "--n-gpu-layers", "all" if prioritize_gpu else str(gpu_layers), "--flash-attn", "auto",
           "--cache-type-k", cache_type, "--cache-type-v", cache_type,
           "--fit-target", str(margin), "--fit-ctx", "2048"]
    if device:
        cmd += ["--device", device]
    env = os.environ.copy()
    env["PATH"] = str(server_dir) + os.pathsep + env.get("PATH", "")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45, env=env,
                                cwd=str(server_dir), creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-1500:])
        args = shlex.split(result.stdout.strip())
        context = bounded_context(int(args[args.index("-c") + 1]))
        fitted_layers = int(args[args.index("-ngl") + 1])
        # Explicit layer choices remain untouched; -1 allows native fitting/offload.
        return context, fitted_layers if gpu_layers == -1 and not prioritize_gpu else gpu_layers
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, RuntimeError) as error:
        log.warning("Context preflight unavailable; using native server fitting: %s", error)
        return (AUTO_CONTEXT_CAP if prioritize_gpu else 0), gpu_layers


def require_gpu_device(server_dir: Path) -> None:
    binary = server_dir / ("llama-server.exe" if sys.platform == "win32" else "llama-server")
    try:
        result = subprocess.run([str(binary), "--list-devices"], capture_output=True,
                                text=True, timeout=20, cwd=str(server_dir),
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        if result.returncode == 0 and re.search(r"(?im)^\s*(?:CUDA|Vulkan|Metal|ROCm|HIP|SYCL|OpenCL|MUSA|CANN)\d*\s*:", result.stdout):
            return
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("Nao foi possivel verificar a GPU para priorizar sua execucao.") from error
    raise RuntimeError("Priorizar execucao na GPU requer uma GPU compativel com o runtime. Desative a opcao para usar a CPU.")


def runtime_context(properties: dict, log_tail: str) -> int:
    settings = properties.get("default_generation_settings") or {}
    value = settings.get("n_ctx")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    # Older servers expose the effective slot size only in their startup log.
    import re
    matches = re.findall(r"\bn_ctx(?:_per_seq)?\s*=\s*(\d+)", log_tail)
    if matches and int(matches[-1]) > 0:
        return int(matches[-1])
    raise RuntimeError("Could not verify the context size applied by llama.cpp")


def is_memory_failure(error: Exception) -> bool:
    text = str(error).lower()
    return any(term in text for term in ("out of memory", "failed to alloc", "cannot alloc", "not enough memory", "allocation failed"))
