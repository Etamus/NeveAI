"""Exercise cached/offline setup and a real launch from a path with spaces."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import psutil

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend/neveai/venv/Scripts/python.exe"
state = json.loads((ROOT / ".desktop/installed.json").read_text())
sandbox = ROOT / "logs" / ("webview2 packaging space " + uuid.uuid4().hex[:8])
(sandbox / "desktop").mkdir(parents=True)
(sandbox / "static/static").mkdir(parents=True)
(sandbox / ".desktop/downloads").mkdir(parents=True)
for file in (ROOT / "desktop").iterdir():
    if file.is_file():
        shutil.copy2(file, sandbox / "desktop" / file.name)
shutil.copy2(ROOT / "neve_window.py", sandbox / "neve_window.py")
os.link(ROOT / "static/static/faviconbar.ico", sandbox / "static/static/faviconbar.ico")
for name in ("runtime.cab", "sdk.zip"):
    os.link(ROOT / ".desktop/downloads" / name, sandbox / ".desktop/downloads" / name)
runtime_source = ROOT / ".desktop" / state["runtime"]
runtime_target = sandbox / ".desktop" / state["runtime"]
for source in runtime_source.rglob("*"):
    target = runtime_target / source.relative_to(runtime_source)
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, target)
(sandbox / ".desktop/installed.json").write_text(json.dumps(state))
environment = os.environ.copy()
environment.update(HTTPS_PROXY="http://127.0.0.1:1", HTTP_PROXY="http://127.0.0.1:1")
for key in ("NEVE_WEBVIEW2_DEBUG_PORT", "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"):
    environment.pop(key, None)
first = subprocess.run([str(PYTHON), str(sandbox / "desktop/setup_runtime.py")], cwd=sandbox, env=environment, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
assert first.returncode == 0, first.stdout.decode(errors="replace") + first.stderr.decode(errors="replace")
assert b"Baixando" not in first.stdout
second = subprocess.run([str(PYTHON), str(sandbox / "desktop/setup_runtime.py")], cwd=sandbox, env=environment, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
assert second.returncode == 0 and b"ja estao integros" in second.stdout
ready = sandbox / "logs/webview2/packaging-ready.tmp"
ready.parent.mkdir(parents=True, exist_ok=True)
environment["NEVE_WINDOW_READY_FILE"] = str(ready)
wrapper = subprocess.Popen([str(PYTHON), str(sandbox / "neve_window.py")], cwd=sandbox, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    deadline = time.monotonic() + 30
    while not ready.exists():
        assert wrapper.poll() is None, "Packaged launcher exited early"
        assert time.monotonic() < deadline, "Packaged window was not ready"
        time.sleep(0.1)
    host = next(process for process in psutil.Process(wrapper.pid).children(recursive=True) if process.name() == "NeveAI.Window.exe")
    user32 = ctypes.windll.user32
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def close(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == host.pid and user32.IsWindowVisible(hwnd):
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return True
    user32.EnumWindows(callback(close), 0)
    assert wrapper.wait(timeout=10) == 0
    result = {"offline_setup": True, "path_with_spaces": True, "idempotent_setup": True, "native_ready": True, "clean_exit": True, "sandbox": str(sandbox)}
    (ROOT / "logs/webview2-packaging-results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
finally:
    if wrapper.poll() is None:
        for child in psutil.Process(wrapper.pid).children(recursive=True):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        wrapper.terminate()
