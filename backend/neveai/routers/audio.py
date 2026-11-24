import json
import logging
import os
import uuid
import shutil
from functools import lru_cache
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from neveai.config import (
    CACHE_DIR,
    WHISPER_COMPUTE_TYPE,
    WHISPER_LANGUAGE,
    WHISPER_MODEL_DIR,
    WHISPER_MULTILINGUAL,
    WHISPER_VAD_FILTER,
)
from neveai.constants import ERROR_MESSAGES
from neveai.env import DEVICE_TYPE
from neveai.utils.access_control import has_permission
from neveai.utils.auth import get_verified_user
from neveai.utils.misc import strict_match_mime_type

router = APIRouter()
log = logging.getLogger(__name__)

_transcription_slot = Lock()
DICTATION_MAX_BYTES = 4 * 1024 * 1024
_dictation_slot = Lock()


@lru_cache(maxsize=1)
def _dictation_model(name):
    from faster_whisper import WhisperModel

    options = dict(device="cpu", compute_type="int8", cpu_threads=2, download_root=WHISPER_MODEL_DIR)
    try:
        return WhisperModel(name, local_files_only=True, **options)
    except Exception:
        return WhisperModel(name, **options)


def _dictation_samples(source):
    import av
    import numpy as np

    rate = 16000
    samples = np.empty(95 * rate, dtype=np.float32)
    length = 0
    resampler = av.AudioResampler(format="flt", layout="mono", rate=rate)

    def append(frames):
        nonlocal length
        for frame in frames:
            end = length + frame.samples
            if end > samples.size:
                raise HTTPException(413, "Dictation recording is too long.")
            samples[length:end] = frame.to_ndarray().ravel()
            length = end

    with av.open(source, mode="r") as audio:
        for frame in audio.decode(audio=0):
            append(resampler.resample(frame))
        append(resampler.resample(None))
    return samples[:length]


@router.post("/dictation")
def dictation(
    request: Request,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    user=Depends(get_verified_user),
):
    if user.role != "admin" and not has_permission(
        user.id, "chat.stt", request.app.state.config.USER_PERMISSIONS
    ):
        raise HTTPException(403, ERROR_MESSAGES.ACCESS_PROHIBITED)
    if not file.size or file.size > DICTATION_MAX_BYTES:
        raise HTTPException(413, "Invalid dictation recording size.")
    supported = request.app.state.config.STT_SUPPORTED_CONTENT_TYPES
    format_type = (file.content_type or "").split(";", 1)[0].lower().strip()
    if format_type not in {"audio/webm", "audio/mp4", "audio/ogg"} or not strict_match_mime_type(
        supported, format_type
    ):
        raise HTTPException(400, ERROR_MESSAGES.FILE_NOT_SUPPORTED)
    if not _dictation_slot.acquire(blocking=False):
        raise HTTPException(429, "Dictation is already being transcribed.")
    try:
        # Decode the upload directly; do not add raw speech or transcripts to the audio cache.
        samples = _dictation_samples(file.file)
        if not samples.size:
            return {"text": ""}
        model = _dictation_model(request.app.state.config.WHISPER_MODEL or "base")
        segments, _ = model.transcribe(
            samples, language=language or WHISPER_LANGUAGE, beam_size=3,
            vad_filter=True, condition_on_previous_text=False,
        )
        return {"text": " ".join(segment.text.strip() for segment in segments).strip()}
    except HTTPException:
        raise
    except Exception as error:
        log.exception("Dictation failed")
        raise HTTPException(400, "Transcription failed.") from error
    finally:
        _dictation_slot.release()


def set_faster_whisper_model(model: str, auto_update: bool = False):
    if not model:
        return None
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log.warning("faster_whisper is not installed; local transcription is unavailable")
        return None

    options = {
        "model_size_or_path": model,
        "device": DEVICE_TYPE if DEVICE_TYPE == "cuda" else "cpu",
        "compute_type": WHISPER_COMPUTE_TYPE,
        "download_root": WHISPER_MODEL_DIR,
        "local_files_only": not auto_update,
    }
    try:
        return WhisperModel(**options)
    except Exception:
        options["local_files_only"] = False
        return WhisperModel(**options)


def _transcription_blocks(file_path, block_seconds=600):
    """Decode once, yielding bounded mono PCM views for synchronous consumption."""
    import av
    import numpy as np

    rate = 16000
    capacity = rate * block_seconds
    pcm = np.empty(capacity, dtype=np.float32)
    used = 0
    resampler = av.AudioResampler(format="flt", layout="mono", rate=rate)

    def append(frames):
        nonlocal used
        for frame in frames:
            samples = frame.to_ndarray().ravel()
            while len(samples):
                count = min(len(samples), capacity - used)
                pcm[used:used + count] = samples[:count]
                used += count
                samples = samples[count:]
                if used == capacity:
                    # Prefer a quiet 20 ms window near the boundary rather than splitting a word.
                    window = 320
                    tail = pcm[-rate:].reshape(-1, window)
                    cut = capacity - rate + int(np.argmin(np.mean(tail * tail, axis=1))) * window + window // 2
                    yield pcm[:cut]
                    used -= cut
                    pcm[:used] = pcm[cut:].copy()

    with av.open(file_path) as source:
        for frame in source.decode(audio=0):
            yield from append(resampler.resample(frame))
        yield from append(resampler.resample(None))
    if used:
        yield pcm[:used]


def transcribe(
    request: Request, file_path: str, metadata: Optional[dict] = None, user=None
) -> dict:
    results = []
    try:
        with _transcription_slot:
            if request.app.state.faster_whisper_model is None:
                request.app.state.faster_whisper_model = set_faster_whisper_model(
                    request.app.state.config.WHISPER_MODEL
                )
            model = request.app.state.faster_whisper_model
            if model is None:
                raise RuntimeError("O modelo local de transcricao nao pode ser carregado")
            language = (metadata or {}).get("language") or WHISPER_LANGUAGE
            for samples in _transcription_blocks(file_path):
                segments, _ = model.transcribe(
                    samples, beam_size=5, vad_filter=WHISPER_VAD_FILTER,
                    language=language, multilingual=WHISPER_MULTILINGUAL,
                )
                text = "".join(segment.text for segment in segments).strip()
                if text:
                    results.append(text)
        result = {"text": " ".join(results)}
        with open(os.path.splitext(file_path)[0] + ".json", "w", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False)
        return result
    except HTTPException:
        raise
    except Exception as error:
        log.exception("Transcription failed")
        raise HTTPException(status_code=400, detail="Transcription failed.") from error


@router.post("/transcriptions")
def transcription(
    request: Request,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    user=Depends(get_verified_user),
):
    if user.role != "admin" and not has_permission(
        user.id, "chat.stt", request.app.state.config.USER_PERMISSIONS
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    supported_types = request.app.state.config.STT_SUPPORTED_CONTENT_TYPES
    if not strict_match_mime_type(supported_types, file.content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.FILE_NOT_SUPPORTED,
        )

    try:
        safe_name = os.path.basename(file.filename) if file.filename else ""
        extension = safe_name.rsplit(".", 1)[-1] if "." in safe_name else ""
        filename = f"{uuid.uuid4()}.{extension}"
        file_dir = os.path.join(CACHE_DIR, "audio", "transcriptions")
        os.makedirs(file_dir, exist_ok=True)
        file_path = os.path.join(file_dir, filename)
        if not os.path.realpath(file_path).startswith(os.path.realpath(file_dir)):
            raise ValueError("Invalid file path detected")
        with open(file_path, "wb") as output:
            shutil.copyfileobj(file.file, output, length=1024 * 1024)

        metadata = {"language": language} if language else None
        result = transcribe(request, file_path, metadata, user)
        return {**result, "filename": os.path.basename(file_path)}
    except HTTPException:
        raise
    except Exception as error:
        log.exception(error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcription failed.",
        ) from error
