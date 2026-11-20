import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from neveai.routers import haru_voice, llamacpp, stable_diffusion
from neveai.utils.voice_priority import VoiceBusy, primary_gpu_work, voice_slot


SILENT = bytes(6400)
VOICE = (np.sin(np.arange(3200) / 24) * 5000).astype("<i2").tobytes()


@pytest.mark.parametrize(("language", "persona"), [
    ("pt", "Seu nome \u00e9 Neve. Voc\u00ea responde por Neve. Fala em portugu\u00eas brasileiro, com clareza e naturalidade."),
    ("en", "Your name is Neve. You answer to Neve. Speak English clearly and naturally."),
])
def test_voice_uses_neve_card_with_spontaneous_opening(language, persona):
    options = {
        "type": "start", "sample_rate": 24000, "language": language, "voice": "neve",
        "name": "Neve", "gender": "female", "seed": 987, "temperature": 0.7,
        "max_seconds": 900, "speak_first": True, "persona": persona,
    }
    if language == "pt":
        options["eop_bias"] = 0.3
    assert haru_voice._dialogue_options(24000, language) == options


def test_fresh_install_uses_the_bundled_gguf_without_a_reference_recording(monkeypatch, tmp_path):
    monkeypatch.delenv("NEVE_HARU_REFERENCE", raising=False)
    monkeypatch.setattr(haru_voice, "VOICE_PROFILE", tmp_path / "legacy.voice.gguf")
    monkeypatch.setattr(haru_voice, "CUSTOM_PROFILES", tmp_path / "profiles")
    bundled = haru_voice.BUNDLED_VOICE_PROFILE
    with bundled.open("rb") as file:
        assert file.read(4) == b"GGUF"
    assert haru_voice._reference("new-user") == bundled

    monkeypatch.setattr(haru_voice, "BUNDLED_VOICE_PROFILE", tmp_path / "missing.voice.gguf")
    with pytest.raises(haru_voice.VoiceError, match="not found"):
        haru_voice._reference("new-user")


def test_relay_passes_opening_pcm_and_leaves_long_playback_and_silence_alone():
    async def run():
        inbound = asyncio.Queue()
        outbound = asyncio.Queue()
        sent = []

        class Runtime:
            async def send(self, pcm):
                sent.append(pcm)
                await inbound.put(pcm)

            async def __aiter__(self):
                while True:
                    yield await inbound.get()

        client = asyncio.Queue()
        ws = SimpleNamespace(receive=client.get, send_bytes=outbound.put, send_json=AsyncMock())
        await inbound.put(VOICE)
        task = asyncio.create_task(haru_voice._relay(ws, Runtime()))
        assert await asyncio.wait_for(outbound.get(), 1) == VOICE
        assert sent == []
        for pcm in [SILENT] + [VOICE] * 230 + [SILENT] * 90 + [VOICE] * 25:
            await client.put({"type": "websocket.receive", "bytes": pcm})
            assert await asyncio.wait_for(outbound.get(), 1) == pcm
            assert sent[-1] == pcm
        await client.put({"type": "websocket.receive", "text": "stop"})
        assert await task is True
        ws.send_json.assert_not_awaited()

    asyncio.run(run())


def test_foreground_waits_for_release_and_rejects_a_new_voice_session():
    async def run():
        observed = []
        async with voice_slot() as stop:
            async def foreground():
                async with primary_gpu_work():
                    observed.append("foreground")
                    with pytest.raises(VoiceBusy):
                        async with voice_slot():
                            pytest.fail("Voice interrupted a foreground job")

            task = asyncio.create_task(foreground())
            await stop.wait()
            assert observed == []
            observed.append("released")
        await task
        assert observed == ["released", "foreground"]
        async with voice_slot():
            pass

    asyncio.run(run())


def test_voice_memory_check_does_not_unload_llm_or_sum_gpus(monkeypatch):
    gib = 1024**3
    unload = AsyncMock()
    monkeypatch.setattr(llamacpp, "model_manager", SimpleNamespace(
        get_loaded_model_id=lambda: "local/llm", unload_model=unload
    ))
    monkeypatch.setattr(llamacpp, "_get_vram_info", lambda: {
        "available": True, "gpus": [{"free": 6 * gib}, {"free": 6 * gib}]
    })
    with pytest.raises(haru_voice.VoiceError, match="Not enough"):
        asyncio.run(haru_voice._check_voice_memory())
    monkeypatch.setattr(llamacpp, "_get_vram_info", lambda: {
        "available": True, "gpus": [{"free": 8 * gib}]
    })
    asyncio.run(haru_voice._check_voice_memory())
    unload.assert_not_awaited()


def test_disabled_image_route_does_not_interrupt_voice():
    async def run():
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            config=SimpleNamespace(ENABLE_STABLE_DIFFUSION=False)
        )))
        async with voice_slot() as stop:
            with pytest.raises(HTTPException) as denied:
                await asyncio.wait_for(stable_diffusion.generate_image(request, None, None), 1)
            assert denied.value.status_code == 403
            assert not stop.is_set()

    asyncio.run(run())
