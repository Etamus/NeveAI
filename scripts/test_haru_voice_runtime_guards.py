"""Opt-in GPU test. Uses an isolated API and never changes model presets or voice files."""

import asyncio
import sys
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.routers import haru_voice, llamacpp
from neveai.utils import middleware

app = FastAPI()
app.include_router(haru_voice.router)
MODEL = sys.argv[1]
with wave.open(sys.argv[2], "rb") as fixture:
    assert (fixture.getframerate(), fixture.getnchannels(), fixture.getsampwidth()) == (24000, 1, 2)
    spoken = fixture.readframes(fixture.getnframes())
headers = {"origin": "http://testserver"}


@app.post("/prepare-model")
async def prepare_model():
    await llamacpp.model_manager.load_model(MODEL, n_ctx=2048, mmproj_filename="")
    return llamacpp.model_manager.get_loaded_model_id()


@app.post("/text")
async def text():
    model = llamacpp.model_manager.get_loaded_model_id()
    generator = await llamacpp.model_manager.chat_completion(
        model, [{"role": "user", "content": "Say hello in one short sentence."}],
        stream=True, max_tokens=24, no_think=True,
    )
    collected = [chunk async for chunk in generator]
    return {"model": model, "completed": bool(collected) and collected[-1].strip() == "data: [DONE]"}


@app.post("/drop-model")
async def drop_model():
    if model := llamacpp.model_manager.get_loaded_model_id():
        await llamacpp.model_manager.unload_model(model)


@app.post("/take-media-slot")
async def take_media_slot():
    await middleware._acquire_media_generation_slot(lambda: asyncio.sleep(0))
    middleware._release_media_generation_slot(True)


def begin(ws):
    ws.send_json({"sample_rate": 24000})
    assert ws.receive_json()["type"] == "preparing"
    return ws.receive_json()


def answer(ws, pcm):
    audible = 0
    for offset in range(0, len(pcm), 6400):
        ws.send_bytes(pcm[offset:offset + 6400].ljust(6400, b"\0"))
        response = ws.receive()
        assert "bytes" in response, response
        audible += any(response["bytes"])
    return audible


with patch.object(haru_voice, "get_current_user", new=AsyncMock(
    return_value=SimpleNamespace(role="user", id="isolated-runtime-test")
)):
    with TestClient(app) as client:
        try:
            reply = client.post("/prepare-model")
            assert reply.is_success, reply.text
            model = reply.json()
            assert model
            with client.websocket_connect("/voice", headers=headers) as ws:
                event = begin(ws)
                if event["type"] == "started":
                    assert len(ws.receive_bytes()) == 6400
                    response = client.post("/text").json()
                    assert response == {"model": model, "completed": True}, response
                    assert ws.receive_json() == {"type": "error", "message": haru_voice.FOREGROUND_BUSY}
                    print("PASS: Haru coexisted with loaded Qwen, yielded for real streaming; Qwen stayed loaded", flush=True)
                else:
                    assert event == {"type": "error", "message": "Not enough free GPU memory for voice mode."}, event
                    assert client.post("/text").json() == {"model": model, "completed": True}
                    print("PASS: Haru refused insufficient VRAM; Qwen stayed loaded and streamed", flush=True)
        finally:
            assert client.post("/drop-model").is_success

        with client.websocket_connect("/voice", headers=headers) as ws:
            assert begin(ws)["type"] == "started"
            assert len(ws.receive_bytes()) == 6400
            assert client.post("/take-media-slot").is_success
            assert ws.receive_json() == {"type": "error", "message": haru_voice.FOREGROUND_BUSY}
            print("PASS: actual Haru process yielded before the shared media slot was returned", flush=True)

        with client.websocket_connect("/voice", headers=headers) as ws:
            assert begin(ws)["type"] == "started"
            assert len(ws.receive_bytes()) == 6400
            answer(ws, bytes(48000 * 3))
            answer(ws, spoken + bytes(48000 * 10))
            print("PASS: microphone PCM and real dialogue without automatic cut or reset", flush=True)
