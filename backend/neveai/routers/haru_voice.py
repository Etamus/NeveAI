"""An on-demand, same-origin bridge to the local speech.cpp Haru runtime."""

import asyncio
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import zipfile
from math import gcd
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import soundfile as sf
from anyio import CancelScope
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

from neveai.config import CACHE_DIR, DATA_DIR
from neveai.utils.auth import get_current_user, get_verified_user
from neveai.utils.media_standby import _finish_before_cancelling
from neveai.utils.model_availability import media_is_busy
from neveai.utils.pinned_media_asset import ensure_pinned_asset
from neveai.utils.voice_priority import VoiceBusy, voice_slot

log = logging.getLogger(__name__)
router = APIRouter()
VERSION = "0.11.0"
WEIGHTS = "Haru-4B-Q8_0.gguf"
VOICE_PROFILE = DATA_DIR / "haru-voice" / "neve.voice.gguf"
BUNDLED_VOICE_PROFILE = Path(__file__).resolve().parents[1] / "voice_assets" / "neve.voice.gguf"
CUSTOM_PROFILES = DATA_DIR / "haru-voice" / "profiles"
MAX_VOICE_UPLOAD = 12 * 1024 * 1024
VOICE_SEED = 987
FOREGROUND_BUSY = "Voice mode gives priority to chat and media generation."
ASSETS = {
    ("Windows", "amd64"): ("windows-x64-vulkan", "b64f498179fc46d08149317eaea9fe6f24e6fa0cd194557b374c97e76ccc9c67"),
    ("Linux", "x86_64"): ("linux-x64-vulkan", "9c01a35a0c79d36ca29abe379029c71b0cfb950cbc9da835863f5f7d28c81ae8"),
    ("Darwin", "arm64"): ("macos-arm64-metal", "3ffe12c4398fa9265abdbf673e2e1ee32b04f52cde151d5388833ac3296c69c0"),
}
_prepare_lock = threading.Lock()
_session = asyncio.Lock()
_profile_update = asyncio.Lock()


def _custom_profile(user_id):
    key = hashlib.sha256(str(user_id).encode()).hexdigest()
    return CUSTOM_PROFILES / f"{key}.voice.gguf"


def _reference(user_id=None):
    if user_id is not None and (custom := _custom_profile(user_id)).is_file():
        return custom.resolve()
    configured = os.environ.get("NEVE_HARU_REFERENCE")
    target = Path(configured) if configured else (
        VOICE_PROFILE if VOICE_PROFILE.is_file() else BUNDLED_VOICE_PROFILE
    )
    if not target.is_file():
        raise VoiceError("Neve's voice profile was not found.")
    return target.resolve()


def _dialogue_options(rate, language="pt"):
    language = "en" if language == "en" else "pt"
    options = {
        "type": "start", "sample_rate": rate, "language": language, "voice": "neve",
        "name": "Neve", "gender": "female", "seed": VOICE_SEED, "temperature": 0.7,
        "max_seconds": 900, "speak_first": True,
        "persona": (
            "Your name is Neve. You answer to Neve. Speak English clearly and naturally."
            if language == "en"
            else "Seu nome \u00e9 Neve. Voc\u00ea responde por Neve. Fala em portugu\u00eas brasileiro, com clareza e naturalidade."
        ),
    }
    if language == "pt":
        # Higher values caused prolonged talking on silent input in Portuguese.
        options["eop_bias"] = 0.3
    return options


def _prepare_runtime():
    system = platform.system()
    asset = ASSETS.get((system, platform.machine().lower()))
    if asset is None:
        raise VoiceError("Voice mode is not supported on this platform.")
    root = CACHE_DIR / "haru_voice"
    name, expected = asset
    runtime = root / f"speech-{VERSION}-{name}"
    executable = "speech.exe" if system == "Windows" else "speech"
    with _prepare_lock:
        root.mkdir(parents=True, exist_ok=True)
        binary = next(runtime.rglob(executable), None)
        if binary is None:
            with tempfile.TemporaryDirectory(dir=root) as work:
                stage = Path(work)
                archive = stage / "speech.zip"
                url = f"https://github.com/nyosegawa/speech.cpp/releases/download/v{VERSION}/{runtime.name}.zip"
                with urllib.request.urlopen(url, timeout=30) as response, archive.open("wb") as out:
                    shutil.copyfileobj(response, out)
                with archive.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                        raise ValueError("Unexpected speech.cpp release checksum")
                unpack = stage / "runtime"
                with zipfile.ZipFile(archive) as bundle:
                    for entry in bundle.infolist():
                        (unpack / entry.filename).resolve().relative_to(unpack.resolve())
                    bundle.extractall(unpack)
                for path in unpack.rglob("*"):
                    if path.is_file() and (path.name == executable or path.suffix in (".so", ".dylib")):
                        path.chmod(0o755)
                relative = next(unpack.rglob(executable)).relative_to(unpack)
                unpack.rename(runtime)
                binary = runtime / relative
        weights = ensure_pinned_asset(
            root, WEIGHTS, 6623102720,
            "c372a527e63ca4251429a48863535b8bca03ebd6f414bbf31f28a9d175349934",
            [("sakasegawa/Haru-4B-GGUF", "fc026182f7bbfaa0400b2d44358a5e9e327b957f")],
        )
    return binary, weights


def _prepare(user_id=None):
    reference = _reference(user_id)
    return (*_prepare_runtime(), reference)


class VoiceError(RuntimeError):
    pass


def _same_origin(ws):
    origin = urlsplit(ws.headers.get("origin", ""))
    return origin.scheme in {"http", "https"} and origin.netloc == ws.headers.get("host")


def _normalize_voice(source, output):
    try:
        with sf.SoundFile(source) as clip:
            if (clip.format not in {"WAV", "WAVEX", "FLAC", "OGG", "MP3"}
                or not 1 <= clip.channels <= 8 or not 8000 <= clip.samplerate <= 96000
                or not 3 <= clip.frames / clip.samplerate <= 60):
                raise VoiceError("Choose 3 to 60 seconds of WAV, MP3, FLAC or OGG audio.")
            audible, blocks = 0, []
            for block in clip.blocks(blocksize=8192, dtype="float32", always_2d=True):
                if not np.isfinite(block).all():
                    raise VoiceError("Could not read this voice recording.")
                mono = block.mean(axis=1)
                audible += np.count_nonzero(np.abs(mono) > 0.005)
                blocks.append(mono)
            if audible < clip.samplerate * 0.3:
                raise VoiceError("No clear audio was found in the recording.")
            rate = clip.samplerate
            mono = np.concatenate(blocks)
            if rate != 24000:
                try:
                    from scipy.signal import resample_poly
                except ImportError:
                    # The runtime can still resample on installations without SciPy.
                    pass
                else:
                    divisor = gcd(rate, 24000)
                    mono = resample_poly(mono, 24000 // divisor, rate // divisor)
                    rate = 24000
            sf.write(output, np.clip(mono, -1.0, 1.0), rate, subtype="PCM_16")
    except (sf.LibsndfileError, ValueError, RuntimeError) as error:
        if isinstance(error, VoiceError):
            raise
        raise VoiceError("Could not read this voice recording.") from error


def _import_profile(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as work:
        wav = Path(work) / "reference.wav"
        output = Path(work) / "voice.gguf"
        _normalize_voice(source, wav)
        binary, weights = _prepare_runtime()
        result = subprocess.run(
            [str(binary), "voice", str(weights), str(wav), str(output), "--device", "cpu", "--threads", "2"],
            cwd=binary.parent, capture_output=True, timeout=60,
            **({"creationflags": 0x08000000} if os.name == "nt" else {}),
        )
        if result.returncode or not output.is_file():
            raise VoiceError("Could not create a voice profile from this recording.")
        output.replace(destination)


@router.get("/voice/profile")
async def get_voice_profile(user=Depends(get_verified_user)):
    return {"custom": _custom_profile(user.id).is_file()}


@router.post("/voice/profile")
async def import_voice_profile(request: Request, file: UploadFile, user=Depends(get_verified_user)):
    if not _same_origin(request):
        raise HTTPException(403, "Invalid origin")
    if not file.size or file.size > MAX_VOICE_UPLOAD:
        raise HTTPException(413, "The voice recording must be under 12 MB.")
    if _profile_update.locked():
        raise HTTPException(409, "A voice profile is already being prepared.")
    async with _profile_update:
        try:
            await asyncio.to_thread(_import_profile, file.file, _custom_profile(user.id))
        except VoiceError as error:
            raise HTTPException(422, str(error)) from error
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            log.exception("Voice profile preparation failed")
            raise HTTPException(500, "Could not create a voice profile from this recording.")
    return {"custom": True}


@router.delete("/voice/profile")
async def remove_voice_profile(request: Request, user=Depends(get_verified_user)):
    if not _same_origin(request):
        raise HTTPException(403, "Invalid origin")
    if _profile_update.locked():
        raise HTTPException(409, "A voice profile is already being prepared.")
    async with _profile_update:
        await asyncio.to_thread(_custom_profile(user.id).unlink, missing_ok=True)
    return {"custom": False}


async def _endpoint(process):
    while line := await process.stderr.readline():
        if match := re.search(rb"Ready at http://127\.0\.0\.1:(\d+)", line):
            return f"ws://127.0.0.1:{int(match[1])}/v1/dialogue"
        log.debug("speech.cpp: %s", line.decode(errors="replace").rstrip())
    raise VoiceError("Could not load Neve.")


async def _relay(ws, upstream):
    async def microphone():
        while True:
            message = await asyncio.wait_for(ws.receive(), 25)
            if message["type"] == "websocket.disconnect":
                return
            if message.get("text") == "stop":
                return True
            frame = message.get("bytes")
            if not frame or len(frame) > 16384 or len(frame) % 2:
                raise VoiceError("Invalid microphone audio.")
            await upstream.send(frame)

    async def playback():
        async for frame in upstream:
            if isinstance(frame, bytes):
                await ws.send_bytes(frame)
            else:
                message = json.loads(frame)
                if message.get("type") == "error":
                    if message.get("error", {}).get("param") == "max_seconds":
                        await ws.send_json({"type": "end"})
                        return
                    log.warning("Haru dialogue: %s", message.get("error"))
                    raise VoiceError("Haru could not keep this voice session running.")
                if message.get("type") in {"started", "end"}:
                    await ws.send_json(message)

    tasks = [asyncio.create_task(microphone()), asyncio.create_task(playback())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        return tasks[0] in done and tasks[0].result() is True
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _prepare_session(ws, operation):
    ready = asyncio.create_task(operation)
    incoming = asyncio.create_task(ws.receive())
    try:
        done, _ = await asyncio.wait((ready, incoming), return_when=asyncio.FIRST_COMPLETED)
        if incoming in done:
            if incoming.result()["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()
            raise VoiceError("Invalid microphone audio.")
        return ready.result()
    finally:
        for task in (ready, incoming):
            task.cancel()
        await asyncio.gather(ready, incoming, return_exceptions=True)


async def _check_voice_memory():
    from neveai.routers.llamacpp import _get_vram_info, model_manager

    info = await asyncio.to_thread(_get_vram_info)
    loaded = model_manager.get_loaded_model_id() is not None
    if info["available"]:
        # The Q8 runtime used about 7 GiB on the reference system. Leave space for
        # dialogue state, desktop rendering and short driver allocations.
        if min(gpu["free"] for gpu in info["gpus"]) < 8 * 1024**3:
            raise VoiceError("Not enough free GPU memory for voice mode.")
    elif loaded:
        # On hardware without a reliable device memory reading, don't guess
        # whether two loaded models fit (especially on unified memory).
        raise VoiceError("Not enough free GPU memory for voice mode.")


@router.websocket("/voice")
async def voice_session(ws: WebSocket):
    user = await get_current_user(ws, None, None) if _same_origin(ws) else None
    if user is None or user.role not in {"admin", "user"}:
        await ws.close(code=1008)
        return
    await ws.accept()
    if _session.locked():
        await ws.send_json({"type": "error", "message": "A voice session is already active."})
        await ws.close()
        return
    async with _session:
        async def dialogue(options, binary, weights, reference):
            rate = int(options["sample_rate"])
            if not 8000 <= rate <= 96000:
                raise VoiceError("Invalid microphone audio.")
            await _check_voice_memory()
            process = None

            async def launch():
                nonlocal process
                process = await asyncio.create_subprocess_exec(
                    str(binary), "serve", str(weights), "--host", "127.0.0.1", "--port", "0",
                    "--add-voice", f"neve={reference}", stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE, cwd=binary.parent,
                    **({"creationflags": 0x08000000} if os.name == "nt" else {}),
                )

            try:
                await _finish_before_cancelling(launch())
                endpoint = await _prepare_session(ws, asyncio.wait_for(_endpoint(process), 120))
                async with connect(endpoint, proxy=None, max_size=65536, close_timeout=1) as upstream:
                    await upstream.send(json.dumps(_dialogue_options(rate, options.get("language"))))
                    return await _relay(ws, upstream)
            finally:
                if process is not None:
                    with CancelScope(shield=True):
                        if process.returncode is None:
                            try:
                                process.kill()
                            except ProcessLookupError:
                                pass
                        await _finish_before_cancelling(process.communicate())

        async def conversation(options):
            if media_is_busy():
                raise VoiceError(FOREGROUND_BUSY)
            await ws.send_json({"type": "preparing"})
            assets = await _prepare_session(ws, asyncio.to_thread(_prepare, user.id))
            try:
                async with voice_slot() as stop:
                    if media_is_busy():
                        raise VoiceError(FOREGROUND_BUSY)
                    task = asyncio.create_task(dialogue(options, *assets))
                    stopped = asyncio.create_task(stop.wait())
                    try:
                        done, _ = await asyncio.wait((task, stopped), return_when=asyncio.FIRST_COMPLETED)
                        if stopped in done:
                            raise VoiceError(FOREGROUND_BUSY)
                        return task.result()
                    finally:
                        task.cancel()
                        stopped.cancel()
                        await _finish_before_cancelling(asyncio.gather(task, stopped, return_exceptions=True))
            except VoiceBusy:
                raise VoiceError(FOREGROUND_BUSY) from None

        try:
            options = await asyncio.wait_for(ws.receive_json(), 10)
            while await conversation(options):
                await ws.send_json({"type": "stopped"})
                options = await asyncio.wait_for(ws.receive_json(), 120)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            if isinstance(exc, VoiceError):
                log.info("Voice session ended: %s", exc)
            else:
                log.warning("Haru voice session failed", exc_info=True)
            try:
                await ws.send_json({"type": "error", "message": str(exc) if isinstance(exc, VoiceError)
                                    else "Could not start or continue voice mode."})
            except (WebSocketDisconnect, RuntimeError, OSError):
                pass
        finally:
            try:
                await ws.close()
            except (WebSocketDisconnect, RuntimeError, OSError):
                pass
