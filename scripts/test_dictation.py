"""Opt-in API test using a local spoken WAV fixture and the actual CPU recognizer."""

import io
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import av
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.routers import audio


def webm(path):
    with wave.open(str(path), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24000)
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").repeat(2)
    output = io.BytesIO()
    with av.open(output, "w", format="webm") as container:
        stream = container.add_stream("libopus", rate=48000)
        stream.layout = "mono"
        for offset in range(0, len(pcm), 960):
            samples = pcm[None, offset:offset + 960]
            frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
            frame.sample_rate = 48000
            container.mux(stream.encode(frame))
        container.mux(stream.encode(None))
    return output.getvalue()


if __name__ == "__main__":
    app = FastAPI()
    app.include_router(audio.router)
    app.state.config = SimpleNamespace(STT_SUPPORTED_CONTENT_TYPES=[], WHISPER_MODEL="base")
    app.dependency_overrides[audio.get_verified_user] = lambda: SimpleNamespace(role="admin")
    clip = webm(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "logs/haru-question-0.wav")
    cache = Path(audio.CACHE_DIR) / "audio" / "transcriptions"
    before = set(cache.glob("*"))
    with TestClient(app) as client:
        def send(payload, mime="audio/webm"):
            return client.post("/dictation", files={"file": ("dictation.webm", payload, mime)},
                               data={"language": "pt"})

        assert send(b"").status_code == 413
        assert send(bytes(audio.DICTATION_MAX_BYTES + 1)).status_code == 413
        assert send(clip, "image/png").status_code == 400
        assert send(b"invalid container").status_code == 400
        result = send(clip)
        assert result.status_code == 200, result.text
        print("CPU result:", result.json())
        assert result.json()["text"]
    assert set(cache.glob("*")) == before
    print("PASS: recognized a WebM recording without creating a transcription cache file")
