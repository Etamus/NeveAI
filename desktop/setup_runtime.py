"""Install the pinned app-local WebView2 and compile its small Windows host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".desktop"
MANIFEST = ROOT / "desktop/runtime.json"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inside_store(path):
    resolved = path.resolve()
    resolved.relative_to(STORE.resolve())
    if resolved == STORE.resolve():
        raise ValueError("Refusing an operation on the desktop store root")
    return resolved


def download(url, target, digest):
    if target.is_file() and sha256(target) == digest:
        return
    partial = inside_store(target.with_suffix(target.suffix + ".part"))
    print("Baixando " + target.name, flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "NeveAI-Installer"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as stream:
        shutil.copyfileobj(response, stream, 1024 * 1024)
    if sha256(partial) != digest:
        partial.unlink()
        raise RuntimeError("Falha de integridade: " + target.name)
    partial.replace(target)


def source_key(config):
    parts = [MANIFEST, ROOT / "desktop/NeveWindow.cs", ROOT / "desktop/app.manifest", ROOT / "static/static/faviconbar.ico"]
    return hashlib.sha256("".join(sha256(path) for path in parts).encode()).hexdigest()[:20]


def runtime_valid(state, runtime, full=False):
    try:
        records = state["runtime_files"]
        for name in ("msedgewebview2.exe", "msedge.dll", "icudtl.dat", "resources.pak"):
            record = records[name]
            file = inside_store(runtime / name)
            if not file.is_file() or file.stat().st_size != record["size"]:
                return False
            if full and sha256(file) != record["sha256"]:
                return False
        return True
    except (OSError, KeyError, TypeError, ValueError):
        return False


def validate(config, full=False):
    try:
        state = json.loads((STORE / "installed.json").read_text(encoding="utf-8"))
        if state["source_key"] != source_key(config) or state["runtime_version"] != config["runtime_version"]:
            return False
        host = inside_store(STORE / state["host"])
        required = {str((host.parent / name).relative_to(STORE.resolve())).replace("\\", "/") for name in ("NeveAI.Window.exe", "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll", "WebView2Loader.dll")}
        if not required.issubset(state["files"]):
            return False
        for name, digest in state["files"].items():
            path = inside_store(STORE / name)
            if not path.is_file() or sha256(path) != digest:
                return False
        runtime = inside_store(STORE / state["runtime"])
        return runtime_valid(state, runtime, full)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def setup():
    if sys.platform != "win32" or os.environ.get("PROCESSOR_ARCHITEW6432", os.environ.get("PROCESSOR_ARCHITECTURE", "")).lower() not in {"amd64", "x64"}:
        raise RuntimeError("A janela do NeveAI requer Windows x64.")
    config = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if str(ROOT).startswith("\\\\"):
        raise RuntimeError("WebView2 Fixed requer uma pasta local, nao um compartilhamento de rede.")
    if validate(config, full=True):
        print("WebView2 Fixed e janela nativa ja estao integros.", flush=True)
        return
    STORE.mkdir(exist_ok=True)
    downloads = STORE / "downloads"
    downloads.mkdir(exist_ok=True)
    download(config["runtime_url"], downloads / "runtime.cab", config["runtime_sha256"])
    download(config["sdk_url"], downloads / "sdk.zip", config["sdk_sha256"])
    stage = inside_store(STORE / ("staging-" + uuid.uuid4().hex))
    stage.mkdir()
    try:
        try:
            old_state = json.loads((STORE / "installed.json").read_text(encoding="utf-8"))
            runtime = inside_store(STORE / old_state["runtime"])
            reuse_runtime = old_state["runtime_version"] == config["runtime_version"] and runtime_valid(old_state, runtime, full=True)
        except (OSError, ValueError, KeyError, TypeError):
            reuse_runtime = False
        if not reuse_runtime:
            runtime = inside_store(STORE / ("runtime-" + config["runtime_version"] + "-x64-" + uuid.uuid4().hex[:8]))
            unpack = stage / "runtime"
            unpack.mkdir()
            print("Extraindo WebView2 Fixed " + config["runtime_version"], flush=True)
            result = subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32/expand.exe"), str(downloads / "runtime.cab"), "-F:*", str(unpack)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError("Falha ao extrair WebView2: " + result.stderr.decode(errors="replace"))
            candidates = list(unpack.rglob("msedgewebview2.exe"))
            if len(candidates) != 1:
                raise RuntimeError("Estrutura inesperada do runtime WebView2.")
            if runtime.exists():
                raise RuntimeError("Runtime incompleto encontrado; preserve a pasta e execute a reparacao manual: " + str(runtime))
            candidates[0].parent.replace(runtime)
        signature = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "desktop/verify-runtime.ps1"), "-RuntimePath", str(runtime)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if signature.returncode:
            raise RuntimeError("A assinatura Microsoft do WebView2 nao foi validada.")
        sdk = stage / "sdk"
        with zipfile.ZipFile(downloads / "sdk.zip") as package:
            for item in package.infolist():
                (sdk / item.filename).resolve().relative_to(sdk.resolve())
            package.extractall(sdk)
        host = stage / "host"
        host.mkdir()
        for name in ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll"):
            shutil.copy2(sdk / "lib/net462" / name, host / name)
        shutil.copy2(sdk / "runtimes/win-x64/native/WebView2Loader.dll", host / "WebView2Loader.dll")
        for name in ("LICENSE.txt", "NOTICE.txt"):
            shutil.copy2(sdk / name, host / name)
        csc = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        if not csc.is_file():
            raise RuntimeError(".NET Framework 4.x do Windows ausente. Repare os componentes do Windows.")
        print("Compilando janela WebView2", flush=True)
        command = [str(csc), "/nologo", "/target:winexe", "/platform:x64", "/optimize+", "/out:" + str(host / "NeveAI.Window.exe"),
                   "/win32manifest:" + str(ROOT / "desktop/app.manifest"), "/win32icon:" + str(ROOT / "static/static/faviconbar.ico"),
                   "/r:System.dll", "/r:System.Core.dll", "/r:System.Drawing.dll", "/r:System.Windows.Forms.dll", "/r:System.Web.Extensions.dll",
                   "/r:" + str(host / "Microsoft.Web.WebView2.Core.dll"), "/r:" + str(host / "Microsoft.Web.WebView2.WinForms.dll"), str(ROOT / "desktop/NeveWindow.cs")]
        result = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace"))
        destination = inside_store(STORE / ("host-" + source_key(config) + "-" + uuid.uuid4().hex[:8]))
        host.replace(destination)
        # AppContainer read/execute ACL required for unpackaged Fixed on Windows 10.
        result = subprocess.run(["icacls.exe", str(runtime), "/grant", "*S-1-15-2-2:(OI)(CI)(RX)", "*S-1-15-2-1:(OI)(CI)(RX)"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError("Nao foi possivel definir as permissoes do WebView2 Fixed.")
        files = {str(path.relative_to(STORE)).replace("\\", "/"): sha256(path) for path in destination.iterdir() if path.suffix.lower() in {".dll", ".exe"}}
        state = {"runtime_version": config["runtime_version"], "runtime": str(runtime.relative_to(STORE)),
                 "host": str((destination / "NeveAI.Window.exe").relative_to(STORE)), "source_key": source_key(config), "files": files,
                 "runtime_files": {name: {"size": (runtime / name).stat().st_size, "sha256": sha256(runtime / name)} for name in ("msedgewebview2.exe", "msedge.dll", "icudtl.dat", "resources.pak")}}
        temporary = STORE / "installed.json.tmp"
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(STORE / "installed.json")
        print("WebView2 Fixed pronto.", flush=True)
    finally:
        shutil.rmtree(inside_store(stage))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        sys.exit(0 if validate(json.loads(MANIFEST.read_text(encoding="utf-8"))) else 1)
    import msvcrt
    STORE.mkdir(exist_ok=True)
    with (STORE / "setup.lock").open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        deadline = time.monotonic() + 1800
        while True:
            try:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Outro instalador esta usando os componentes da janela.")
                time.sleep(1)
        try:
            setup()
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
