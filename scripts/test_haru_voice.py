"""Opt-in GPU smoke: feed a local recording, do not open a microphone or save a chat."""

import sys
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.routers import haru_voice

app = FastAPI()
app.include_router(haru_voice.router)
with patch.object(haru_voice, "get_current_user", new=AsyncMock(return_value=SimpleNamespace(role="user", id="fixture"))):
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/voice", headers={"origin": "https://outside.test"}):
                raise AssertionError("Cross-origin connection was accepted")
        except WebSocketDisconnect as exc:
            assert exc.code == 1008, exc

        with client.websocket_connect("/voice", headers={"origin": "http://testserver"}) as ws:
            ws.send_json({"sample_rate": 48000})
            assert ws.receive_json()["type"] == "preparing"
            start = ws.receive_json()
            assert start == {"type": "started", "sample_rate": 24000, "frame_samples": 3200}, start
            assert len(ws.receive_bytes()) == 6400
            with wave.open(sys.argv[1], "rb") as voice:
                assert (voice.getnchannels(), voice.getsampwidth(), voice.getframerate()) == (1, 2, 48000)
                ws.send_bytes(bytes(3840))  # Resampler lookahead at 48 kHz.
                speaking = 0
                for _ in range(165):
                    frame = voice.readframes(6400).ljust(12800, b"\x00")
                    ws.send_bytes(frame)
                    answer = ws.receive_bytes()
                    assert len(answer) == 6400
                    if max(abs(int.from_bytes(answer[i:i+2], "little", signed=True))
                           for i in range(0, len(answer), 2)) > 500:
                        speaking += 1
                assert speaking > 0, "Haru did not produce audible PCM"
        print(f"PASS: reference loaded, {speaking} audible frames, same-origin check, clean disconnect")
