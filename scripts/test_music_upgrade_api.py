"""Use the production music adapter/API and LM without writing a chat or library."""
import asyncio
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
REPORT = ROOT / "logs/runtime-upgrade-20261029"


async def main():
    from neveai.routers.music_generation import ace_step_runtime as runtime, ACE_STEP_MODEL
    import soundfile as sf
    import numpy as np

    async def progress(message):
        print(message, flush=True)
    start = time.perf_counter()
    result = await runtime.generate(
        "Crie uma musica pop acustica com voz feminina em portugues.", progress,
        music_plan={"caption": "Gentle acoustic pop, clear female singing in Portuguese, guitar and soft drums, warm intimate studio sound.",
                    "lyrics": "[Verse]\nO vento leva a minha voz\nPor entre as ruas de cristal\nEu sigo a luz dentro de n\u00f3s\nAt\u00e9 chegar ao meu quintal", "instrumental": False},
    )
    samples, rate = sf.read(io.BytesIO(result["audio"]))
    assert np.isfinite(samples).all() and np.abs(samples).max() > 0.01
    path = REPORT / "music-api.flac"
    path.write_bytes(result["audio"])
    summary = dict(model=ACE_STEP_MODEL, lm_model=runtime._detected_lm_model, elapsed_seconds=time.perf_counter()-start,
                   duration_seconds=len(samples)/rate, sample_rate=rate, content_type=result["content_type"],
                   task_type=result["task_type"], metadata=result["metadata"], path=str(path))
    (REPORT / "music-api.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
