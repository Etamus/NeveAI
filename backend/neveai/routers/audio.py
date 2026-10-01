import json
import logging
import os
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub")

try:
    from pydub import AudioSegment
    from pydub.utils import mediainfo
except ImportError:
    AudioSegment = None
    mediainfo = None

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

MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024


def is_audio_conversion_required(file_path: str) -> bool:
    supported_formats = {"flac", "m4a", "mp3", "mp4", "mpeg", "wav", "webm"}
    if not os.path.isfile(file_path) or mediainfo is None:
        return False
    try:
        info = mediainfo(file_path)
        codec_name = info.get("codec_name", "").lower()
        codec_type = info.get("codec_type", "").lower()
        codec_tag = info.get("codec_tag_string", "").lower()
        if codec_name == "aac" and codec_type == "audio" and codec_tag == "mp4a":
            return True
        return codec_name not in supported_formats
    except Exception as error:
        log.warning("Unable to inspect audio format: %s", error)
        return False


def convert_audio_to_mp3(file_path: str) -> Optional[str]:
    if AudioSegment is None:
        return None
    try:
        output_path = os.path.splitext(file_path)[0] + ".mp3"
        AudioSegment.from_file(file_path).export(output_path, format="mp3")
        return output_path
    except Exception as error:
        log.warning("Unable to convert audio to MP3: %s", error)
        return None


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


def transcription_handler(
    request: Request, file_path: str, metadata: Optional[dict] = None, user=None
) -> dict:
    if request.app.state.faster_whisper_model is None:
        request.app.state.faster_whisper_model = set_faster_whisper_model(
            request.app.state.config.WHISPER_MODEL
        )
    model = request.app.state.faster_whisper_model
    if model is None:
        raise RuntimeError("O modelo local de transcricao nao pode ser carregado")

    language = (metadata or {}).get("language") or WHISPER_LANGUAGE
    segments, info = model.transcribe(
        file_path,
        beam_size=5,
        vad_filter=WHISPER_VAD_FILTER,
        language=language,
        multilingual=WHISPER_MULTILINGUAL,
    )
    log.info(
        "Detected language '%s' with probability %f",
        info.language,
        info.language_probability,
    )
    data = {"text": "".join(segment.text for segment in segments).strip()}
    transcript_file = os.path.splitext(file_path)[0] + ".json"
    with open(transcript_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False)
    return data


def compress_audio(file_path: str) -> str:
    if os.path.getsize(file_path) <= MAX_FILE_SIZE or AudioSegment is None:
        return file_path
    base = os.path.splitext(file_path)[0]
    compressed_path = f"{base}_compressed.mp3"
    audio = AudioSegment.from_file(file_path).set_frame_rate(16000).set_channels(1)
    audio.export(compressed_path, format="mp3", bitrate="32k")
    return compressed_path


def split_audio(
    file_path: str, max_bytes: int, format: str = "mp3", bitrate: str = "32k"
) -> list[str]:
    file_size = os.path.getsize(file_path)
    if file_size <= max_bytes:
        return [file_path]
    if AudioSegment is None:
        raise RuntimeError("pydub is required to split large audio files")

    audio = AudioSegment.from_file(file_path)
    duration_ms = len(audio)
    chunk_ms = max(int(duration_ms * (max_bytes / file_size)) - 1000, 1000)
    chunks = []
    start = 0
    index = 0
    base = os.path.splitext(file_path)[0]

    while start < duration_ms:
        end = min(start + chunk_ms, duration_ms)
        chunk_path = f"{base}_chunk_{index}.{format}"
        audio[start:end].export(chunk_path, format=format, bitrate=bitrate)
        while os.path.getsize(chunk_path) > max_bytes and end - start > 5000:
            end = start + ((end - start) // 2)
            audio[start:end].export(chunk_path, format=format, bitrate=bitrate)
        if os.path.getsize(chunk_path) > max_bytes:
            os.remove(chunk_path)
            raise RuntimeError("Audio chunk cannot be reduced below max file size")
        chunks.append(chunk_path)
        start = end
        index += 1
    return chunks


def transcribe(
    request: Request, file_path: str, metadata: Optional[dict] = None, user=None
) -> dict:
    if is_audio_conversion_required(file_path):
        converted_path = convert_audio_to_mp3(file_path)
        if converted_path:
            file_path = converted_path

    try:
        file_path = compress_audio(file_path)
        chunk_paths = split_audio(file_path, MAX_FILE_SIZE)
    except Exception as error:
        log.exception(error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(error),
        ) from error

    results = []
    try:
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(
                    transcription_handler, request, chunk_path, metadata, user
                )
                for chunk_path in chunk_paths
            ]
            for future in futures:
                results.append(future.result())
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error transcribing chunk: {error}",
        ) from error
    finally:
        for chunk_path in chunk_paths:
            if chunk_path != file_path and os.path.isfile(chunk_path):
                try:
                    os.remove(chunk_path)
                except OSError:
                    pass

    return {"text": " ".join(result["text"] for result in results)}


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
            output.write(file.file.read())

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
