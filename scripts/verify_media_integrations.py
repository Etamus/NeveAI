"""Opt-in GPU smoke for the actual installed media runtimes; never saves a chat."""
import asyncio
import base64
import io
import os
from pathlib import Path
import sys
import tempfile
import shutil
import json
import struct
import time

import av
import httpx
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    cache = ROOT / "backend/data/cache"
    evidence = ROOT / "logs/media-integration-check"
    evidence.mkdir(exist_ok=True)
    os.environ["DATA_DIR"] = str(evidence)
    os.environ["DATABASE_URL"] = "sqlite:///" + (evidence / "isolated.db").as_posix()
    from neveai import config
    config.CACHE_DIR = cache
    from neveai.routers import image_quality_generation as quality, model3d_generation as mesh, video_quality_generation as video

    async def idle():
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8080") as client:
            for endpoint, key in [("/api/tasks","tasks"), ("/llamacpp/models/loaded","models")]:
                response = await client.get(endpoint)
                response.raise_for_status()
                if response.json()[key]:
                    raise RuntimeError("Test requires an idle GPU/backend: " + endpoint)

    async def progress(*args):
        print(*args, flush=True)

    image = cache / "mesh_generation/smoke/reference.png"
    if "image" in sys.argv:
        await idle()
        start = time.monotonic()
        reference = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()
        result = await quality.NeveImage21Runtime().run("Troque a cor do objeto para azul, preservando o fundo.",
                                                       "1:1", [reference], None, progress)
        data = base64.b64decode(result.split(",", 1)[1])
        with Image.open(io.BytesIO(data)) as frame:
            assert max(ImageStat.Stat(frame.convert("RGB")).stddev) > 3
            print("IMAGE", frame.size, round(time.monotonic()-start, 2), flush=True)
        (evidence / "edit.png").write_bytes(data)
    if "mesh" in sys.argv:
        from unittest.mock import patch
        await mesh.mesh_runtime.prepare(progress)
        start = time.monotonic()
        with patch("neveai.utils.pinned_media_asset.hf_hub_download", side_effect=AssertionError("network on warm path")):
            await mesh.mesh_runtime.prepare(progress)
        print("MESH warm/offline", round(time.monotonic()-start, 4), flush=True)
    if "mesh-generate" in sys.argv:
        await idle()
        await mesh.mesh_runtime.prepare(progress)
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="pixal3d-", dir=evidence) as tmp:
            job = Path(tmp)
            with Image.open(image) as ref:
                alpha = ref.convert("RGBA").getchannel("A").getextrema()[0] < 255
                ref.save(job / "reference.png")
            output = await mesh.mesh_runtime.generate(job, alpha, progress)
            with output.open("rb") as stream:
                magic, version, length, chunk_len, chunk = struct.unpack("<4sIII4s", stream.read(20))
                assert magic == b"glTF" and version == 2 and length == output.stat().st_size and chunk == b"JSON"
                manifest = json.loads(stream.read(chunk_len))
                vertices = sum(manifest["accessors"][p["attributes"]["POSITION"]]["count"]
                               for m in manifest["meshes"] for p in m["primitives"])
                assert vertices > 0 and manifest["buffers"]
            shutil.copyfile(output, evidence / "restored-model.glb")
            print("MESH GENERATED", vertices, round(time.monotonic()-start, 2), flush=True)
    if "video" in sys.argv:
        await idle()
        start = time.monotonic()
        runtime = video.video15_runtime
        try:
            await runtime.prepare(progress)
            result = await runtime.generate("A slow camera push towards the object. Soft ambient sound.",
                progress, image=("reference.png", image.read_bytes(), "image/png"))
            data = result["video"]
            with av.open(io.BytesIO(data)) as container:
                assert container.streams.audio and container.streams.video
                frame = next(container.decode(video=0)).to_image()
                assert max(ImageStat.Stat(frame).stddev) > 3
            with av.open(io.BytesIO(data)) as container:
                assert any(abs(frame.to_ndarray()).max() > 0 for frame in container.decode(audio=0))
            (evidence / "video.mp4").write_bytes(data)
            print("VIDEO + AUDIO", len(data), round(time.monotonic()-start, 2), flush=True)
        finally:
            await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
