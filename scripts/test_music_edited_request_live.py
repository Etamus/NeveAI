"""Validate the real music planner and XL runtime after reloading an idle chat model."""
import asyncio
import io
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
REPORT = ROOT / "logs/music-edit-20261030"
REPORT.mkdir(parents=True, exist_ok=True)


async def main():
    from neveai.utils import middleware
    from neveai.routers.music_generation import ace_step_runtime

    base = "http://127.0.0.1:8080"
    model = "local/Qwen3.5 9B MTP UDQ4_K_XL"
    profile = dict(filename="Qwen3.5 9B MTP UDQ4_K_XL.gguf", n_gpu_layers=99, n_ctx=8192,
                   cache_type="q8_0", context_shift="off", speculative_decoding="off", token_prediction="off")
    events = []
    async def progress(message):
        print(message, flush=True)
    async with httpx.AsyncClient(base_url=base, timeout=300) as client:
        loaded = (await client.get("/llamacpp/models/loaded")).json()["models"]
        if loaded:
            raise RuntimeError("Run with the chat model unloaded; refusing to change another active session")
        catalog = (await client.get("/api/models")).json()["data"]
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            MODELS={item["id"]: item for item in catalog}, config=SimpleNamespace(TASK_MODEL=None))))
        async def native_completion(_request, form_data, **kwargs):
            response = await client.post("/api/chat/completions", json=form_data)
            response.raise_for_status()
            return response.json()
        prompt = "Crie uma cancao pop acustica em portugues sobre estrelas, com voz feminina e uma letra curta de quatro versos."
        async def plan(value):
            with patch.object(middleware, "generate_chat_completion", side_effect=native_completion):
                return await middleware._prepare_music_generation_plan(request, {"model": model}, None, value)
        try:
            try:
                await plan(prompt)
            except RuntimeError as exc:
                events.append({"step": "before_reload", "expected_failure": str(exc)})
            else:
                raise AssertionError("Expected the unloaded model to reject planning")
            start = time.perf_counter()
            response = await client.post("/llamacpp/models/load", json=profile)
            response.raise_for_status()
            events.append({"step": "load_selected_model", "model": response.json().get("id")})
            prepared = await plan(prompt)
            assert prepared["lyrics"].strip() and not prepared["instrumental"], prepared
            events.append({"step": "edited_plan", "plan": prepared})
            response = await client.post("/llamacpp/models/unload", json={"model_id": model})
            response.raise_for_status()
            result = await ace_step_runtime.generate(prompt, progress, music_plan=prepared)
            audio = result["audio"]
            samples, rate = sf.read(io.BytesIO(audio))
            assert np.isfinite(samples).all() and float(np.abs(samples).max()) > 0.01
            (REPORT / "edited-music.flac").write_bytes(audio)
            events.append({"step": "music_generated", "duration": len(samples)/rate, "sample_rate": rate, "seconds": time.perf_counter()-start})
            # A second edited request must also work after the generator released VRAM.
            response = await client.post("/llamacpp/models/load", json=profile)
            response.raise_for_status()
            prepared_again = await plan(prompt.replace("estrelas", "amanhecer"))
            assert prepared_again["lyrics"].strip()
            events.append({"step": "second_edit_after_standby", "plan": prepared_again})
        finally:
            await ace_step_runtime.cancel()
            await client.post("/llamacpp/models/unload", json={"model_id": model})
            (REPORT / "result.json").write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(events, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
