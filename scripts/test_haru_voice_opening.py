"""Opt-in GPU test. Uses a local voice profile but never opens its source WAV."""

import os
import sys
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

app = FastAPI()
app.include_router(haru_voice.router)
headers = {"origin": "http://testserver"}


def get_frames(client, samples=None):
    with client.websocket_connect("/voice", headers=headers) as ws:
        ws.send_json({"sample_rate": 24000})
        assert ws.receive_json()["type"] == "preparing"
        assert ws.receive_json()["type"] == "started"
        audio = [ws.receive_bytes()]
        for frame in samples if samples is not None else [bytes(6400)] * 25:
            ws.send_bytes(frame)
            response = ws.receive()
            assert "bytes" in response, response
            audio.append(response["bytes"])
        return audio


def audible_frames(frames):
    return sum(max(map(abs, array("h", frame)), default=0) > 500 for frame in frames)


runtime_defaults = haru_voice._dialogue_options
assert runtime_defaults(24000)["speak_first"] is True
with patch.dict(os.environ), \
     patch.object(haru_voice, "VOICE_PROFILE", ROOT / "missing.voice.gguf"), \
     patch.object(haru_voice, "get_current_user", new=AsyncMock(return_value=SimpleNamespace(role="user", id="fixture"))):
    os.environ.pop("NEVE_HARU_REFERENCE", None)
    assert haru_voice._reference() == haru_voice.BUNDLED_VOICE_PROFILE
    with TestClient(app) as client:
        opening_silence = [bytes(6400)] * 45
        with patch.object(haru_voice, "_dialogue_options", lambda *args: {
            key: value for key, value in runtime_defaults(*args).items() if key != "speak_first"
        }):
            previous = get_frames(client, opening_silence)
        first = get_frames(client, opening_silence)
        second = get_frames(client, opening_silence)
        print(f"Opening with silent mic, audible packets: omitted={audible_frames(previous)}, spontaneous={audible_frames(first)}", flush=True)
        assert audible_frames(first) >= 5, "No sustained spontaneous opening with a silent microphone"
        for path in sys.argv[1:]:
            with wave.open(path, "rb") as recording:
                assert (recording.getframerate(), recording.getnchannels(), recording.getsampwidth()) == (24000, 1, 2)
                speech = recording.readframes(recording.getnframes())
            lead = 6400 * 45
            clip = bytes(lead) + speech + bytes(48000 * 9)
            frames = [clip[i:i+6400].ljust(6400, b"\0") for i in range(0, len(clip), 6400)]
            reply = get_frames(client, frames)
            assert len(reply) == len(frames) + 1 and all(len(frame) == 6400 for frame in reply)
            silence = get_frames(client, [bytes(6400)] * len(frames))
            after_speech = 1 + (lead + len(speech) + 6399) // 6400
            voiced = audible_frames(reply[after_speech:])
            assert voiced >= 5, "No sustained output after the user spoke"
            assert reply[after_speech:] != silence[after_speech:], "No change in PCM after actual user speech"
            print(f"PASS: {voiced} audible packets after speech, distinct from silence: {Path(path).name}", flush=True)
    assert first == second, "Same initial audio and seed produced different PCM"
    print("PASS: stable PCM and bundled profile without WAV")
