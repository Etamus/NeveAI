"""Launch the installer and acknowledge only its first rendered window."""

import os
import subprocess
import tempfile
import time
from pathlib import Path


def launch_installer_update_page(root: Path, timeout: float = 45.0) -> None:
    launcher = root / "launchers" / "instalar.vbs"
    if not launcher.is_file():
        raise FileNotFoundError(f"instalar.vbs not found: {launcher}")
    with tempfile.TemporaryDirectory(prefix="neve-updater-") as directory:
        ready = Path(directory) / "ready"
        env = {**os.environ, "NEVE_INSTALLER_READY_FILE": str(ready)}
        process = subprocess.Popen(
            [str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"),
             "//nologo", str(launcher), "--page", "update"],
            cwd=str(root), close_fds=True, env=env,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if ready.is_file():
                return
            if process.poll() is not None:
                raise RuntimeError("Installer exited before displaying its window")
            time.sleep(0.05)
        raise TimeoutError("Installer did not confirm its window was displayed")
