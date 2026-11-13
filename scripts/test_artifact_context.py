"""Replay the reported edit without changing or saving the user's conversation."""
import json
import re
import sqlite3
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "artifact-context"


def main():
    REPORT.mkdir(exist_ok=True)
    with sqlite3.connect(f"file:{(ROOT / 'backend/data/neve.db').as_posix()}?mode=ro", uri=True) as db:
        chat = json.loads(db.execute("SELECT chat FROM chat WHERE id=?", ("882cbf0e-84b1-4ca5-a102-eab8545b06d3",)).fetchone()[0])
    messages = chat["history"]["messages"]
    first = next(message for message in messages.values() if message.get("role") == "assistant")
    original = messages[first["parentId"]]
    edit = next(message for message in messages.values() if message.get("parentId") == first["id"])
    with httpx.Client(base_url="http://127.0.0.1:8080", timeout=300) as client:
        loaded = client.get("/llamacpp/models/loaded").raise_for_status().json()["models"]
        model = next(item for item in loaded if item["id"] == "local/Qwen3.5-9B-UD-Q4_K_XL")
        keys = ["filename", "n_gpu_layers", "mmproj_filename", "cache_type", "speculative_decoding", "token_prediction", "context_shift", "prioritize_gpu"]
        request = {key: model[key] for key in keys}
        request["n_ctx"] = 16384
        result = client.post("/llamacpp/models/load", json=request).raise_for_status().json()
        print(json.dumps({"stage": "loaded", "n_ctx": result.get("n_ctx"), "filename": model["filename"]}), flush=True)
        replay = [{"role": message["role"], "content": message["content"]} for message in [original, first, edit]]
        body = {"model": model["id"], "messages": replay, "stream": True, "max_tokens": -1, "no_think": True, "temperature": 0.4, "min_p": 0.1, "seed": 42}
        output, finish, usage = "", None, None
        start = time.perf_counter()
        with client.stream("POST", "/llamacpp/chat/completions", json=body) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                event = json.loads(line[6:])
                usage = event.get("usage") or usage
                for choice in event.get("choices", []):
                    output += choice.get("delta", {}).get("content") or ""
                    finish = choice.get("finish_reason") or finish
        (REPORT / "edit-response.txt").write_text(output, encoding="utf-8")
        after = client.get("/llamacpp/models/loaded").raise_for_status().json()["models"]
        current = next(item for item in after if item["id"] == model["id"])
        assert current["n_ctx"] == 16384
        assert all(current[key] == model[key] for key in keys)
        complete = bool(re.search(r"</html>\s*\n```", output, re.I))
        report = {"n_ctx_before": model["n_ctx"], "n_ctx_after": current["n_ctx"], "other_load_options_preserved": True, "seconds": time.perf_counter()-start, "characters": len(output), "finish_reason": finish, "usage": usage, "complete_html_and_fence": complete}
        (REPORT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
        assert finish == "stop" and complete, "The edit did not finish with a complete HTML document"


if __name__ == "__main__":
    main()
