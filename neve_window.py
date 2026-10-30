"""Launch the bundled WebView2 Fixed host. No browser app-mode fallback."""
import ctypes
import json
import os
import subprocess
import sys

from desktop.setup_runtime import MANIFEST, STORE, ROOT, validate
from desktop.profile_migration import migrate


def launch():
    config = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not validate(config):
        raise RuntimeError("A janela WebView2 esta ausente ou desatualizada. Execute instalar.bat para instalar/reparar os componentes da janela.")
    migrate(ROOT)
    state = json.loads((STORE / "installed.json").read_text(encoding="utf-8"))
    host = (STORE / state["host"]).resolve()
    runtime = (STORE / state["runtime"]).resolve()
    host.relative_to(STORE.resolve())
    runtime.relative_to(STORE.resolve())
    arguments = [str(host), "--root", str(ROOT), "--runtime", str(runtime),
                 "--profile", str(ROOT / "logs/webview2/profile")]
    ready = os.environ.get("NEVE_WINDOW_READY_FILE", "")
    if ready:
        arguments.extend(["--ready-file", ready])
    environment = os.environ.copy()
    for key in ("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER", "WEBVIEW2_USER_DATA_FOLDER", "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"):
        environment.pop(key, None)
    environment["WEBVIEW2_DEFAULT_BACKGROUND_COLOR"] = "FF000000"
    return subprocess.call(arguments, cwd=ROOT, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)


if __name__ == "__main__":
    try:
        sys.exit(launch())
    except Exception as error:
        log = ROOT / "logs/webview2-launcher.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(str(error) + "\n")
        ctypes.windll.user32.MessageBoxW(None, str(error), "NeveAI", 0x10)
        sys.exit(1)
