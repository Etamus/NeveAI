"""Opt-in speech.cpp CPU smoke: imports into an isolated user profile directory."""

import asyncio
import io
import json
import sys
import tempfile
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.routers import haru_voice


def sample():
    with wave.open(sys.argv[1], "rb") as wav:
        params = wav.getparams()
        pcm = wav.readframes(params.nframes)
    result = io.BytesIO()
    with wave.open(result, "wb") as wav:
        wav.setparams(params)
        wav.writeframes(pcm if params.nframes >= params.framerate * 3 else pcm * 2)
    return result.getvalue()


def speak(session, path, language):
    session.send_json({"sample_rate": 24000, "language": language})
    assert session.receive_json()["type"] == "preparing"
    started = session.receive_json()
    assert started["type"] == "started", started
    assert len(session.receive_bytes()) == 6400
    with wave.open(str(path), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24000)
        clip = wav.readframes(wav.getnframes())
    # Let the spontaneous opening play before sending the test question.
    tail = 48000 * 9
    pcm = bytes(48000 * 6) + clip + bytes(tail)
    voiced = 0
    for offset in range(0, len(pcm), 6400):
        session.send_bytes(pcm[offset:offset + 6400].ljust(6400, b"\0"))
        response = session.receive()
        assert "bytes" in response, (offset / 48000, response)
        answer = response["bytes"]
        assert len(answer) == 6400
        if offset >= len(pcm) - tail and max(map(abs, array("h", answer))) > 500:
            voiced += 1
    assert voiced >= 5, f"No spoken reply in {language}: {voiced} voiced frames"
    return voiced


async def check_opening():
    pcm = b"\x01\x02" * 3200

    class Upstream:
        async def __aiter__(self):
            for packet in (pcm, json.dumps({"type": "text", "text": "Hum..."}), pcm,
                           json.dumps({"type": "text", "text": " Ol\u00e1!"}), pcm):
                yield packet

    class Client:
        frames = []

        async def receive(self):
            await asyncio.Future()

        async def send_bytes(self, packet):
            self.frames.append(packet)

    ws = Client()
    await haru_voice._relay(ws, Upstream())
    assert ws.frames == [pcm, pcm, pcm], "Spontaneous audio must play from the first frame"


app = FastAPI()
app.include_router(haru_voice.router)
app.dependency_overrides[haru_voice.get_verified_user] = lambda: SimpleNamespace(id="voice-test")
headers = {"origin": "http://testserver"}
default = haru_voice._reference()
portuguese = Path(sys.argv[2])
english = Path(sys.argv[3]) if len(sys.argv) > 3 else None
assert haru_voice._dialogue_options(24000, None)["language"] == "pt"
assert haru_voice._dialogue_options(24000, "ja")["language"] == "pt"
assert haru_voice._dialogue_options(24000, "en")["language"] == "en"
with tempfile.TemporaryDirectory() as folder, patch.object(haru_voice, "CUSTOM_PROFILES", Path(folder)):
    with TestClient(app) as client:
        assert client.get("/voice/profile").json() == {"custom": False}
        assert client.post("/voice/profile", headers={"origin": "https://outside.test"},
                           files={"file": ("voice.wav", b"sample")}).status_code == 403
        with patch.object(haru_voice, "get_current_user",
                          new=AsyncMock(return_value=SimpleNamespace(role="user", id="voice-test"))):
            with client.websocket_connect("/voice", headers=headers) as session:
                print("Default PT:", speak(session, portuguese, "pt"), flush=True)
                session.send_text("stop")
                assert session.receive_json() == {"type": "stopped"}
                response = client.post("/voice/profile", headers=headers, files={"file": ("voice.wav", sample())})
                assert response.status_code == 200, response.text
                assert response.json() == {"custom": True}
                profile = haru_voice._reference("voice-test")
                assert profile != default and profile.read_bytes()[:4] == b"GGUF"
                assert [path.resolve() for path in Path(folder).iterdir()] == [profile]
                assert haru_voice._reference("another-user") == default
                print("Imported PT:", speak(session, portuguese, "pt"), flush=True)
                if english:
                    session.send_text("stop")
                    assert session.receive_json() == {"type": "stopped"}
                    print("Imported EN:", speak(session, english, "en"), flush=True)
                session.send_text("stop")
                assert session.receive_json() == {"type": "stopped"}
                assert client.delete("/voice/profile", headers=headers).json() == {"custom": False}
                assert haru_voice._reference("voice-test") == default
                print("Restored PT:", speak(session, portuguese, "pt"), flush=True)
        assert client.post("/voice/profile", headers=headers,
                           files={"file": ("voice.wav", sample())}).json() == {"custom": True}
        before = profile.read_bytes()
        response = client.post("/voice/profile", headers=headers, files={"file": ("invalid.wav", b"invalid")})
        assert response.status_code == 422, response.text
        assert profile.read_bytes() == before
        assert client.delete("/voice/profile", headers=headers).json() == {"custom": False}
        assert haru_voice._reference("voice-test") == default
        assert not list(Path(folder).iterdir())
        assert default.is_file()
asyncio.run(check_opening())
print("PASS: voice import and rejection, per-user profile, removal, and immediate spontaneous opening")
