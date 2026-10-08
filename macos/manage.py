"""Isolated installer/launcher. No writes outside macos/ and no shared Windows data."""

import argparse
import contextlib
import gzip
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
import uuid
from pathlib import Path

from adapt import adapt_snapshot

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
RUNTIME = HERE / ".runtime"
APP = RUNTIME / "app"
PYTHON = RUNTIME / "venv/bin/python"
NODE_VERSION = "v22.23.3"
STATE = RUNTIME / "installation.json"
LOGS = RUNTIME / "logs"


def checked_path(path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(HERE.resolve()) or resolved == HERE.resolve():
        raise ValueError(f"Escrita fora do ambiente macOS recusada: {path}")
    return resolved


@contextlib.contextmanager
def runtime_lock():
    import fcntl

    checked_path(RUNTIME)
    checked_path(APP)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for name in ("tmp", "data", "logs", "cache"):
        checked_path(RUNTIME / name).mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "runtime.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "O ambiente macOS ja esta em uso. Feche a Neve antes de instalar/reparar."
            )
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def write_json(path, value):
    path = checked_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def download(url, destination, sha256=None):
    if not url.startswith("https://"):
        raise ValueError("Download sem HTTPS recusado")
    destination = checked_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Neve-macOS"})
        with (
            urllib.request.urlopen(request, timeout=180) as response,
            temporary.open("wb") as output,
        ):
            shutil.copyfileobj(response, output)
        if sha256 and hashlib.sha256(temporary.read_bytes()).hexdigest() != sha256:
            raise RuntimeError(f"Checksum incorreto: {destination.name}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Neve-macOS"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def unpack(archive, destination):
    destination = checked_path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                target = (destination / info.filename).resolve()
                if (
                    not target.is_relative_to(destination)
                    or (info.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise ValueError("Caminho inseguro no ZIP")
            package.extractall(destination)
    else:
        with tarfile.open(archive) as package:
            for member in package.getmembers():
                if (
                    not (destination / member.name)
                    .resolve()
                    .is_relative_to(destination)
                ):
                    raise ValueError("Caminho inseguro no TAR")
                if member.issym() or member.islnk():
                    base = destination / member.name if member.issym() else destination
                    target = (
                        (base.parent / member.linkname).resolve()
                        if member.issym()
                        else (base / member.linkname).resolve()
                    )
                    if not target.is_relative_to(destination):
                        raise ValueError("Link externo no TAR")
                elif not (member.isfile() or member.isdir()):
                    raise ValueError("Tipo inseguro no TAR")
            package.extractall(destination, filter="data")


def native_arch():
    if sys.platform != "darwin":
        raise RuntimeError(
            "Exclusivo do macOS; nenhuma instalacao Windows sera modificada."
        )
    arch = platform.machine()
    if arch not in ("arm64", "x86_64"):
        raise RuntimeError(f"Arquitetura nao suportada: {arch}")
    translated = subprocess.run(
        ["/usr/sbin/sysctl", "-in", "sysctl.proc_translated"],
        capture_output=True,
        text=True,
    )
    if translated.stdout.strip() == "1":
        raise RuntimeError("Execute sem Rosetta, com Python ARM64 nativo.")
    if int(platform.mac_ver()[0].split(".")[0]) < 14:
        raise RuntimeError("macOS 14 ou posterior necessario.")
    return arch


def environment():
    env = os.environ.copy()
    env.pop("WEBUI_SECRET_KEY", None)
    env.pop("WEBUI_SECRET_KEY_FILE", None)
    env.update(
        {
            "PYTHONPATH": str(APP / "backend"),
            "PYTHONNOUSERSITE": "1",
            "DATA_DIR": str(RUNTIME / "data"),
            "DATABASE_URL": "sqlite:///" + (RUNTIME / "data/neve.db").as_posix(),
            "PIP_CACHE_DIR": str(RUNTIME / "cache/pip"),
            "npm_config_cache": str(RUNTIME / "cache/npm"),
            "TMPDIR": str(RUNTIME / "tmp"),
            "FRONTEND_BUILD_DIR": str(APP / "build"),
            "HF_HOME": str(RUNTIME / "cache/huggingface"),
            "XDG_CACHE_HOME": str(RUNTIME / "cache"),
            "UV_CACHE_DIR": str(RUNTIME / "cache/uv"),
            "UV_PYTHON_INSTALL_DIR": str(RUNTIME / "python"),
            "NLTK_DATA": str(RUNTIME / "cache/nltk"),
            "TORCH_HOME": str(RUNTIME / "cache/torch"),
            "PYTORCH_ENABLE_MPS_FALLBACK": "1",
            "USE_CUDA_DOCKER": "false",
            "ENV": "production",
            "ENABLE_VIDEO_GENERATION": "false",
            "CORS_ALLOW_ORIGIN": "http://127.0.0.1:8080;http://localhost:8080",
        }
    )
    node = (
        RUNTIME
        / f'tools/node-{NODE_VERSION}-darwin-{ "arm64" if platform.machine() == "arm64" else "x64" }/bin'
    )
    env["PATH"] = os.pathsep.join(
        [
            str(node),
            str(PYTHON.parent),
            str(RUNTIME / "tools/uv"),
            str(RUNTIME / "tools/media"),
            env.get("PATH", ""),
        ]
    )
    return env


def run(args, cwd=APP, emit=print, env=None):
    emit("$ " + " ".join(map(str, args)))
    with subprocess.Popen(
        list(map(str, args)),
        cwd=cwd,
        env=env or environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    ) as proc:
        for line in proc.stdout:
            emit(line.rstrip())
        code = proc.wait()
    if code:
        raise RuntimeError(f"Comando falhou (codigo {code}); consulte o log: {args[0]}")


def snapshot():
    # An allowlist avoids copying credentials, databases, Windows binaries and huge model folders.
    checked_path(APP).mkdir(parents=True, exist_ok=True)
    for name in ("src", "static"):
        target = checked_path(APP / name)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(SOURCE / name, target, symlinks=False)
    target = APP / "backend/neveai"
    if target.exists():
        shutil.rmtree(checked_path(target))
    shutil.copytree(
        SOURCE / "backend/neveai",
        target,
        ignore=shutil.ignore_patterns("venv", ".venv", "__pycache__", "*.pyc"),
    )
    for name in (
        "package.json",
        "package-lock.json",
        "svelte.config.js",
        "vite.config.ts",
        "tailwind.config.js",
        "postcss.config.js",
        "tsconfig.json",
        "LICENSE.txt",
        "version.txt",
        ".npmrc",
    ):
        shutil.copy2(SOURCE / name, APP / name)
    for name in ("models", "mmproj", "logs", "llamacpp-server/bin"):
        (APP / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "runtime_app.py", APP / "backend/neve_macos_app.py")
    adapt_snapshot(APP)


def install_node(arch):
    name = f'node-{NODE_VERSION}-darwin-{ "arm64" if arch == "arm64" else "x64" }'
    binary = RUNTIME / f"tools/{name}/bin/node"
    if binary.exists():
        return binary.parent
    checksums = (
        urllib.request.urlopen(
            f"https://nodejs.org/dist/{NODE_VERSION}/SHASUMS256.txt", timeout=60
        )
        .read()
        .decode()
    )
    archive_name = name + ".tar.gz"
    checksum = next(
        line.split()[0]
        for line in checksums.splitlines()
        if line.split()[-1] == archive_name
    )
    archive = RUNTIME / f"downloads/{archive_name}"
    download(
        f"https://nodejs.org/dist/{NODE_VERSION}/{archive_name}", archive, checksum
    )
    unpack(archive, RUNTIME / "tools")
    binary.chmod(0o755)
    (binary.parent / "npm").resolve().chmod(0o755)
    return binary.parent


def install_media(arch, emit):
    release = get_json(
        "https://api.github.com/repos/eugeneware/ffmpeg-static/releases/tags/b6.1.1"
    )
    architecture = "arm64" if arch == "arm64" else "x64"
    target = checked_path(RUNTIME / "tools/media")
    target.mkdir(parents=True, exist_ok=True)
    for command in ("ffmpeg", "ffprobe"):
        name = f"{command}-darwin-{architecture}.gz"
        asset = next(
            (
                item
                for item in release["assets"]
                if item["name"] == name and item.get("digest")
            ),
            None,
        )
        if not asset:
            raise RuntimeError(f"Binario nativo com checksum ausente: {name}")
        archive = RUNTIME / "downloads" / name
        download(
            asset["browser_download_url"],
            archive,
            asset["digest"].removeprefix("sha256:"),
        )
        with (
            gzip.open(archive, "rb") as source,
            (target / command).open("wb") as output,
        ):
            shutil.copyfileobj(source, output)
        (target / command).chmod(0o755)
        run([target / command, "-version"], emit=emit)
    return release["tag_name"]


def install_llama(arch, emit):
    releases = get_json(
        "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"
    )
    suffix = f'-bin-macos-{ "arm64" if arch == "arm64" else "x64" }.tar.gz'
    for release in releases:
        if release.get("draft"):
            continue
        asset = next(
            (
                a
                for a in release["assets"]
                if a["name"].endswith(suffix) and a.get("digest")
            ),
            None,
        )
        if asset:
            break
    else:
        raise RuntimeError("Nenhum binario macOS verificado do llama.cpp encontrado.")
    emit(f'llama.cpp {release["tag_name"]}: {arch}')
    archive = RUNTIME / "downloads" / asset["name"]
    download(
        asset["browser_download_url"], archive, asset["digest"].removeprefix("sha256:")
    )
    stage = RUNTIME / "llama-stage"
    if stage.exists():
        shutil.rmtree(checked_path(stage))
    unpack(archive, stage)
    server = next(stage.rglob("llama-server"), None)
    if not server:
        raise RuntimeError("llama-server ausente no arquivo oficial.")
    destination = APP / "llamacpp-server/bin"
    for item in server.parent.iterdir():
        if item.is_file():
            shutil.copy2(item, destination / item.name)
            (destination / item.name).chmod(0o755)
    try:
        run([destination / "llama-server", "--version"], emit=emit)
    except (OSError, RuntimeError):
        emit(
            "Binario oficial incompatível com este macOS; compilando o mesmo release localmente."
        )
        run(["/usr/bin/xcrun", "--find", "clang"], emit=emit)
        run([PYTHON, "-m", "pip", "install", "cmake>=3.25,<5"], emit=emit)
        repo = RUNTIME / "sources/llama.cpp"
        if not repo.exists():
            repo.parent.mkdir(parents=True, exist_ok=True)
            run(
                [
                    "/usr/bin/git",
                    "clone",
                    "https://github.com/ggml-org/llama.cpp",
                    repo,
                ],
                emit=emit,
            )
        run(["/usr/bin/git", "-C", repo, "fetch", "--tags"], emit=emit)
        run(
            ["/usr/bin/git", "-C", repo, "checkout", "--detach", release["tag_name"]],
            emit=emit,
        )
        build = repo / ("build-" + release["tag_name"])
        cmake = PYTHON.parent / "cmake"
        run(
            [
                cmake,
                "-S",
                repo,
                "-B",
                build,
                "-DCMAKE_BUILD_TYPE=Release",
                "-DBUILD_SHARED_LIBS=OFF",
                f'-DGGML_METAL={ "ON" if arch == "arm64" else "OFF" }',
                "-DGGML_OPENMP=OFF",
                "-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0",
            ],
            emit=emit,
        )
        run(
            [
                cmake,
                "--build",
                build,
                "--parallel",
                str(min(os.cpu_count() or 2, 8)),
                "--target",
                "llama-server",
                "llama-cli",
                "llama-fit-params",
            ],
            emit=emit,
        )
        for item in (build / "bin").iterdir():
            if item.is_file():
                shutil.copy2(item, destination / item.name)
                (destination / item.name).chmod(0o755)
        run([destination / "llama-server", "--version"], emit=emit)
    (APP / "llamacpp-server/version.txt").write_text(
        release["tag_name"] + "\nmacOS native\n", encoding="utf-8"
    )
    return release["tag_name"]


def install_images(arch, emit):
    # Compile locally: upstream macOS archives can require a newer OS than the user's Mac.
    run(["/usr/bin/xcrun", "--find", "clang"], emit=emit)
    run([PYTHON, "-m", "pip", "install", "cmake>=3.25,<5"], emit=emit)
    repo = RUNTIME / "sources/stable-diffusion.cpp"
    if not repo.exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "/usr/bin/git",
                "clone",
                "--recursive",
                "https://github.com/leejet/stable-diffusion.cpp",
                repo,
            ],
            emit=emit,
        )
    revision = subprocess.check_output(
        ["/usr/bin/git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    cmake = PYTHON.parent / "cmake"
    build = repo / "build-neve"
    run(
        [
            cmake,
            "-S",
            repo,
            "-B",
            build,
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_SHARED_LIBS=OFF",
            f'-DSD_METAL={ "ON" if arch == "arm64" else "OFF" }',
            "-DGGML_OPENMP=OFF",
            "-DGGML_METAL_EMBED_LIBRARY=ON",
            "-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0",
        ],
        emit=emit,
    )
    run(
        [
            cmake,
            "--build",
            build,
            "--config",
            "Release",
            "--parallel",
            str(min(os.cpu_count() or 2, 8)),
        ],
        emit=emit,
    )
    binary = next(build.rglob("sd-cli"), None)
    if not binary:
        raise RuntimeError("Build de imagem terminou sem sd-cli.")
    target = APP / "backend/bin/stable-diffusion-cpp"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, target / "sd-cli")
    for item in binary.parent.iterdir():
        if item.is_file() and item.suffix in (".metal", ".metallib", ".dylib"):
            shutil.copy2(item, target / item.name)
    (target / "sd-cli").chmod(0o755)
    run([target / "sd-cli", "--help"], emit=emit)
    return revision


def requirements(arch):
    from packaging.requirements import Requirement

    by_name = {}
    for name in ("requirements-runtime.txt", "requirements.txt"):
        for line in (
            (SOURCE / "backend" / name).read_text(encoding="utf-8-sig").splitlines()
        ):
            line = line.split("#", 1)[0].strip()
            if line:
                req = Requirement(line)
                by_name[req.name.lower().replace("_", "-")] = line
    by_name.update(
        {
            "torch": "torch==2.11.0" if arch == "arm64" else "torch==2.2.2",
            "torchvision": (
                "torchvision==0.26.0" if arch == "arm64" else "torchvision==0.17.2"
            ),
            "pywebview": "pywebview>=5,<7",
            "pyobjc-framework-cocoa": "pyobjc-framework-Cocoa",
            "pyobjc-framework-webkit": "pyobjc-framework-WebKit",
        }
    )
    if arch != "arm64":
        by_name["numpy"] = "numpy>=1.26,<2"
        by_name["transformers"] = "transformers==4.46.3"
        by_name["sentence-transformers"] = "sentence-transformers==2.7.0"
        by_name["onnxruntime"] = "onnxruntime==1.19.2"
    by_name.pop("pypandoc", None)
    by_name["pypandoc-binary"] = "pypandoc-binary==1.17"
    path = RUNTIME / "requirements-macos.txt"
    path.write_text("\n".join(by_name.values()) + "\n", encoding="utf-8")
    return path


def install(images=True, music=True, emit=print):
    with runtime_lock():
        _install(images, music, emit)


def _install(images=True, music=True, emit=print):
    arch = native_arch()
    STATE.unlink(missing_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    snapshot()
    emit("Instalando dependencias Python nativas...")
    run([PYTHON, "-m", "ensurepip", "--upgrade"], emit=emit)
    run(
        [PYTHON, "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"],
        emit=emit,
    )
    run([PYTHON, "-m", "pip", "install", "-r", requirements(arch)], emit=emit)
    run([PYTHON, "-m", "pip", "check"], emit=emit)
    node = install_node(arch)
    media = install_media(arch, emit)
    run([node / "npm", "ci", "--no-audit", "--no-fund"], emit=emit)
    run(
        [
            node / "node",
            "--max-old-space-size=4096",
            APP / "node_modules/vite/bin/vite.js",
            "build",
        ],
        emit=emit,
    )
    run([node / "npm", "exec", "--", "officecli", "--version"], emit=emit)
    llama = install_llama(arch, emit)
    sd_revision = install_images(arch, emit) if images else None
    config = APP / ".env"
    if not config.exists():
        config.write_text(
            "WEBUI_AUTH=True\nENABLE_SIGNUP=True\nWEBUI_SECRET_KEY="
            + os.urandom(32).hex()
            + "\n",
            encoding="utf-8",
        )
        config.chmod(0o600)
    env = environment()
    env["ENABLE_STABLE_DIFFUSION"] = str(images).lower()
    env["ENABLE_MUSIC_GENERATION"] = str(music).lower()
    # Import validation discovers missing/transitive dependencies before declaring installation complete.
    run(
        [
            PYTHON,
            "-c",
            'import neveai.main; import torch; print("MPS:", torch.backends.mps.is_available())',
        ],
        emit=emit,
        env=env,
    )
    run(
        [
            PYTHON,
            "-c",
            'import nltk; nltk.download("punkt_tab", raise_on_error=True); nltk.download("averaged_perceptron_tagger_eng", raise_on_error=True)',
        ],
        emit=emit,
        env=env,
    )
    write_json(
        STATE,
        {
            "arch": arch,
            "llama": llama,
            "node": NODE_VERSION,
            "media": media,
            "images": images,
            "music": music,
            "sd_revision": sd_revision,
            "installed_at": time.time(),
            "verified_http": False,
        },
    )
    emit("Verificando inicializacao real do backend e frontend...")
    try:
        _start(smoke=True)
    except Exception:
        STATE.unlink(missing_ok=True)
        raise
    state = json.loads(STATE.read_text())
    state["verified_http"] = True
    write_json(STATE, state)
    frozen = subprocess.check_output([str(PYTHON), "-m", "pip", "freeze"], text=True)
    (RUNTIME / "requirements-installed.lock").write_text(frozen, encoding="utf-8")
    emit("Instalacao concluida. Abra iniciar.command.")


def healthy(url, instance=None):
    try:
        with urllib.request.urlopen(
            url + ("/health/macos" if instance else "/health"), timeout=1
        ) as response:
            return response.status == 200 and (
                instance is None or json.load(response).get("instance") == instance
            )
    except (OSError, ValueError):
        return False


def terminate_owned(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def start(browser=False, smoke=False):
    with runtime_lock():
        _start(browser, smoke)


def _start(browser=False, smoke=False):
    native_arch()
    if not STATE.is_file() or not (APP / "build/index.html").is_file():
        raise RuntimeError("Instalacao incompleta. Execute instalar.command.")
    state = json.loads(STATE.read_text())
    if not smoke and not state.get("verified_http"):
        raise RuntimeError(
            "Verificacao HTTP pendente; execute instalar.command para reparar."
        )
    if state["arch"] != platform.machine():
        raise RuntimeError(
            "Reinstale neste Mac; o ambiente pertence a outra arquitetura."
        )
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 8080))
        except OSError:
            raise RuntimeError(
                "Porta 8080 ocupada. Nenhum processo externo foi encerrado."
            )
    env = environment()
    env["ENABLE_STABLE_DIFFUSION"] = str(state["images"]).lower()
    env["ENABLE_MUSIC_GENERATION"] = str(state["music"]).lower()
    instance = uuid.uuid4().hex
    env["NEVE_MACOS_INSTANCE"] = instance
    LOGS.mkdir(parents=True, exist_ok=True)
    url = "http://127.0.0.1:8080"
    with (LOGS / "backend.log").open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [
                str(PYTHON),
                "-m",
                "uvicorn",
                "neve_macos_app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8080",
            ],
            cwd=APP / "backend",
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 600
            while not healthy(url, instance):
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(
                        "Backend nao iniciou; veja macos/.runtime/logs/backend.log."
                    )
                time.sleep(0.25)
            if smoke:
                with urllib.request.urlopen(url + "/", timeout=10) as response:
                    if (
                        response.status != 200
                        or b"<html" not in response.read().lower()
                    ):
                        raise RuntimeError("Frontend nao foi servido corretamente.")
                with urllib.request.urlopen(
                    url + "/api/config", timeout=10
                ) as response:
                    json.load(response)
                print(
                    "PASS: backend proprio, frontend e configuracao HTTP; encerramento limpo."
                )
            elif browser:
                subprocess.run(["/usr/bin/open", url], check=True)
                print("Neve disponivel em " + url + ". Ctrl+C encerra este servidor.")
                proc.wait()
            else:
                import webview

                webview.settings["ALLOW_DOWNLOADS"] = True
                webview.settings["ALLOW_FILE_URLS"] = False
                webview.create_window(
                    "Neve", url, width=1100, height=800, min_size=(360, 420)
                )
                webview.start(
                    gui="cocoa",
                    private_mode=False,
                    storage_path=str(RUNTIME / "browser-state"),
                )
        finally:
            terminate_owned(proc)


class InstallerAPI:
    def __init__(self):
        self.lines = []
        self.running = False
        self.done = False
        self.error = ""
        self.lock = threading.Lock()

    def emit(self, line):
        with self.lock:
            self.lines.append(line)
            self.lines = self.lines[-200:]
        LOGS.mkdir(parents=True, exist_ok=True)
        with (LOGS / "install.log").open("a", encoding="utf-8") as output:
            output.write(line + "\n")

    def status(self):
        with self.lock:
            return {
                "running": self.running,
                "done": self.done,
                "error": self.error,
                "lines": self.lines.copy(),
            }

    def begin(self, images=True, music=True):
        if self.running:
            return False
        self.running = True
        self.done = False
        self.error = ""

        def work():
            try:
                install(bool(images), bool(music), self.emit)
                self.done = True
            except Exception as exc:
                self.error = str(exc)
                self.emit("ERRO: " + self.error)
            finally:
                self.running = False

        threading.Thread(target=work, daemon=False).start()
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["install", "start", "doctor"])
    parser.add_argument("--cli", action="store_true")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--no-images", action="store_true")
    parser.add_argument("--no-music", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    native_arch()
    if args.mode == "install" and not args.cli:
        import webview

        api = InstallerAPI()
        window = webview.create_window(
            "Instalar Neve - macOS",
            str(HERE / "installer.html"),
            js_api=api,
            width=680,
            height=550,
            min_size=(420, 400),
        )
        window.events.closing += lambda: not api.running
        webview.start(gui="cocoa")
    elif args.mode == "install":
        install(not args.no_images, not args.no_music)
    elif args.mode == "start":
        start(args.browser)
    else:
        print(
            json.dumps(
                {
                    "platform": platform.platform(),
                    "python": sys.version,
                    "installation": (
                        json.loads(STATE.read_text()) if STATE.exists() else None
                    ),
                    "data": str(RUNTIME / "data"),
                    "source_untouched": str(SOURCE),
                },
                indent=2,
            )
        )
        if args.smoke:
            start(smoke=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print("ERRO:", exc, file=sys.stderr)
        sys.exit(1)
