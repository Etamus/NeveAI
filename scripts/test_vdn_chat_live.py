"""Exercise real chat dispatch and library registration; remove only this test's file."""
import asyncio
import json
from pathlib import Path
import sys
import time

import httpx

from test_vdn_generation_live import inspect_video

ROOT = Path(__file__).resolve().parents[1]


async def main():
    report = ROOT / "logs/vdn-study-20261031"
    report.mkdir(parents=True, exist_ok=True)
    prompt = ("A young adult woman in a blue jacket walks slowly through a sunlit garden. "
              "Natural face, consistent proportions, gentle tracking camera, realistic motion. No text.")
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8080", timeout=900) as client:
        assert not (await client.get("/api/tasks")).json()["tasks"]
        before = (await client.get("/api/v1/files/generated", params={"kind": "video", "limit": 100})).json()
        previous_ids = {item["id"] for item in before}
        started = time.perf_counter()
        response = await client.post("/api/chat/completions", json={
            "model": "local/Qwen3.5 9B MTP UDQ4_K_XL", "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "features": {"video_generation": True, "video_generation_model": "vdn_h3",
                         "video_generation_resolution": "480p", "video_generation_duration": "5s",
                         "video_generation_aspect_ratio": "9:16"},
        })
        response.raise_for_status()
        after = (await client.get("/api/v1/files/generated", params={"kind": "video", "limit": 100})).json()
        created = [item for item in after if item["id"] not in previous_ids
                   and item.get("meta", {}).get("data", {}).get("prompt") == prompt
                   and item.get("meta", {}).get("data", {}).get("video_model") == "vdn_h3"]
        assert len(created) == 1, dict(response=response.text, new_items=created)
        file = created[0]
        try:
            assert file["meta"]["data"]["source"] == "minimax-h3-vdn-int8"
            media = await client.get(f"/api/v1/files/{file['id']}/content")
            media.raise_for_status()
            output = report / "chat-portrait.mp4"
            output.write_bytes(media.content)
            result = dict(seconds=time.perf_counter()-started, library_registered=True,
                          file=file, inspection=inspect_video(output))
            (report / "chat-live.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result), flush=True)
        finally:
            # The exact id was created by this request and verified by prompt + model.
            deleted = await client.delete(f"/api/v1/files/{file['id']}")
            deleted.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
