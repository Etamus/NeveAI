"""Close only this project's legacy app window, then activate its new host."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop.profile_migration import migrate


def close_legacy():
    profile = str(ROOT / "logs/browser-app").lower()
    targets = {}
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            if (process.info["name"] or "").lower() in {"brave.exe", "chrome.exe", "msedge.exe", "chromium.exe", "opera.exe", "vivaldi.exe"} and any(profile in argument.lower() for argument in process.info["cmdline"] or []):
                targets[process.pid] = process
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    user32 = ctypes.windll.user32
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def close(hwnd, _):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value in targets and user32.IsWindowVisible(hwnd):
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return True
    user32.EnumWindows(callback(close), 0)
    deadline = time.monotonic() + 20
    while any(process.is_running() for process in targets.values()):
        if time.monotonic() >= deadline:
            raise RuntimeError("A janela antiga ainda esta aberta. Nenhum processo foi forcado a encerrar.")
        time.sleep(0.1)
    print(json.dumps({"legacy_closed": True, "matched_processes": len(targets)}), flush=True)


def start():
    ready = ROOT / "logs/webview2/activation-ready.tmp"
    ready.parent.mkdir(parents=True, exist_ok=True)
    ready.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["NEVE_WINDOW_READY_FILE"] = str(ready)
    log = (ROOT / "logs/webview2-activation.log").open("ab")
    process = subprocess.Popen([str(ROOT / "backend/neveai/venv/Scripts/pythonw.exe"), str(ROOT / "neve_window.py")], cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(600):
        if ready.exists():
            print(json.dumps({"webview2_ready": True, "launcher_pid": process.pid}))
            return
        if process.poll() is not None:
            raise RuntimeError("A janela encerrou antes da prontidao; consulte os logs WebView2.")
        time.sleep(0.1)
    raise RuntimeError("A janela nao concluiu a abertura no tempo esperado.")


if __name__ == "__main__":
    close_legacy()
    migrate(ROOT)
    start()
