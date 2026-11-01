"""Validate the production intent router with local inference, without saving chats."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def main():
    spec = importlib.util.spec_from_file_location("intent_fixture", ROOT / "backend/test_web_search_intent.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    scope = fixture.router()
    model = "local/Qwen3.5 9B MTP UDQ4_K_XL"
    results = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8080", timeout=120) as client:
        loaded = (await client.get("/llamacpp/models/loaded")).json()["models"]
        tasks = (await client.get("/api/tasks")).json()["tasks"]
        if loaded or tasks:
            raise RuntimeError("Refusing to disturb an active model or task")
        try:
            response = await client.post("/llamacpp/models/load", json=dict(
                filename="Qwen3.5 9B MTP UDQ4_K_XL.gguf", n_gpu_layers=99, n_ctx=8192,
                cache_type="q8_0", context_shift="off", speculative_decoding="off", token_prediction="off"))
            response.raise_for_status()
            responses = []

            async def complete(request, form_data, **kwargs):
                response = await client.post("/api/chat/completions", json=form_data)
                response.raise_for_status()
                value = response.json()["choices"][0]["message"]["content"]
                responses.append(value)
                return value

            scope["generate_chat_completion"] = complete
            for question, expected in [
                ("Dolar hoje", True), ("Como melhorar este poema?", False),
                ("Qual a capital da Franca?", False), ("Explique recursao", False),
                ("Recomende uma placa de video para comprar", True),
                ("O que e fotossintese?", False),
            ]:
                responses.clear()
                decision = await scope["resolve_web_search_decision"](
                    SimpleNamespace(app=object()), {"model": model}, None, question, question)
                results.append(dict(request=question, expected=expected, decision=decision,
                                    classifier_responses=list(responses)))
                print(json.dumps(results[-1], ensure_ascii=True), flush=True)
            assert all(row["decision"] == row["expected"] for row in results), results
            assert all(row["classifier_responses"] for row in results[2:]), "A classifier call fell back"
        finally:
            response = await client.post("/llamacpp/models/unload", json={"model_id": model})
            response.raise_for_status()
            (ROOT / "logs/web-intent-live-20261031.json").write_text(
                json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
