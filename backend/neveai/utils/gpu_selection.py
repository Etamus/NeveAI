"""Select the dedicated Vulkan adapter when a machine also has integrated graphics."""

import json
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _gpu_priority(name: str) -> int:
    name = name.lower()
    if re.search(r"vega\s*\d+\s*graphics|radeon(?:\(tm\))?\s+graphics|uhd\s+graphics|iris", name):
        return 0
    if re.search(r"\brx\s*\d+|radeon\s+pro\b|\brtx\s*\d+|\bgtx\s*\d+", name):
        return 2
    return 1


@lru_cache(maxsize=1)
def windows_display_adapters() -> list[dict]:
    if os.name != "nt":
        return []
    try:
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                "@(Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM) | ConvertTo-Json -Compress",
            ],
            capture_output=True, text=True, timeout=10, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        values = json.loads(result.stdout)
        return [item for item in (values if isinstance(values, list) else [values]) if isinstance(item, dict)]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def preferred_amd_adapter() -> Optional[dict]:
    adapters = [
        adapter for adapter in windows_display_adapters()
        if re.search(r"amd|radeon|\brx\s*\d+", str(adapter.get("Name") or ""), re.IGNORECASE)
    ]
    if not adapters:
        return None
    return max(adapters, key=lambda item: (
        _gpu_priority(str(item.get("Name") or "")),
        int(item.get("AdapterRAM") or 0),
    ))


def _model_key(name: str) -> str:
    match = re.search(r"\brx\s*(\d+\s*[a-z]*)|\b(vega\s*\d+)", name, re.IGNORECASE)
    return re.sub(r"\W+", "", match.group(0)).lower() if match else ""


def select_vulkan_device(output: str, preferred_name: str = "") -> Optional[str]:
    devices = re.findall(r"(?im)^\s*(vulkan\d+)(?:\t|:\s+)\s*(.+)$", output)
    if not devices:
        return None
    preferred_key = _model_key(preferred_name)
    selected = max(devices, key=lambda item: (
        bool(preferred_key and (
            preferred_key in _model_key(item[1]) or _model_key(item[1]) in preferred_key
        )),
        _gpu_priority(item[1]),
        int(re.search(r"(\d+)\s*MiB", item[1], re.IGNORECASE).group(1))
        if re.search(r"(\d+)\s*MiB", item[1], re.IGNORECASE) else 0,
    ))
    return selected[0]


def preferred_vulkan_device(executable: Path) -> Optional[str]:
    if os.name != "nt" or not executable.is_file():
        return None
    try:
        modified = executable.stat().st_mtime_ns
    except OSError:
        return None
    return _probe_vulkan_device(executable, modified)


@lru_cache(maxsize=8)
def _probe_vulkan_device(executable: Path, modified: int) -> Optional[str]:
    try:
        result = subprocess.run(
            [str(executable), "--list-devices"],
            capture_output=True, text=True, timeout=20, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        preferred = preferred_amd_adapter()
        return select_vulkan_device(
            result.stdout + "\n" + result.stderr,
            str(preferred.get("Name") or "") if preferred else "",
        )
    except (OSError, subprocess.SubprocessError):
        return None
