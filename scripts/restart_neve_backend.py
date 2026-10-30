"""Restart only this workspace's idle backend, preserving its process environment."""
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
matches = []
for connection in psutil.net_connections(kind="tcp"):
    if connection.status == psutil.CONN_LISTEN and connection.laddr.port == 8080 and connection.pid:
        process = psutil.Process(connection.pid)
        if Path(process.cwd()).resolve() == (ROOT / "backend").resolve() and "neveai.main:app" in process.cmdline():
            matches.append(process)
if len(matches) != 1:
    raise RuntimeError("Could not uniquely identify this workspace's backend")
process = matches[0]
environment = process.environ()
parent = process.parent()
process.terminate()
try:
    process.wait(15)
except psutil.TimeoutExpired:
    process.kill()
    process.wait(10)
try:
    if parent and parent.is_running() and "neveai.main:app" in parent.cmdline():
        parent.wait(5)
except (psutil.NoSuchProcess, psutil.TimeoutExpired):
    pass
log = (ROOT / "logs/backend-activation.log").open("ab")
child = subprocess.Popen([
    str(ROOT / "backend/neveai/venv/Scripts/python.exe"), "-m", "uvicorn", "neveai.main:app",
    "--host", "0.0.0.0", "--port", "8080",
], cwd=ROOT / "backend", env=environment, stdout=log, stderr=subprocess.STDOUT,
    **({"creationflags": 0x08000000} if os.name == "nt" else {}))
for _ in range(90):
    if child.poll() is not None:
        raise RuntimeError("Backend startup failed; see logs/backend-activation.log")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2) as response:
            if response.status == 200:
                print(json.dumps({"backend_ready": True, "pid": child.pid}))
                break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("Backend startup timed out")
