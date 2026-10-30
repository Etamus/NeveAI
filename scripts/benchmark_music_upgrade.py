"""Controlled ACE DiT comparison, using the music runtime interpreter."""
import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/data/cache/music_generation/ACE-Step-1.5"
REPORT = ROOT / "logs/runtime-upgrade-20261029"
sys.path.insert(0, str(SOURCE))
os.environ["HF_HOME"] = str(SOURCE.parent / "huggingface")
os.environ["ACESTEP_CHECK_UPDATE"] = "false"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--case", default="instrumental")
    parser.add_argument("--source")
    args = parser.parse_args()
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    import torch
    import soundfile as sf
    import numpy as np

    start = time.perf_counter()
    handler = AceStepHandler()
    status, ok = handler.initialize_service(
        project_root=str(SOURCE), config_path=args.model, device="cuda",
        use_flash_attention=False, compile_model=False, offload_to_cpu=True,
        offload_dit_to_cpu=False, quantization=None,
    )
    if not ok:
        raise RuntimeError(status)
    loaded = time.perf_counter()
    common = dict(duration=20, inference_steps=8, seed=42, thinking=False,
                  use_cot_metas=False, use_cot_caption=False, use_cot_language=False)
    params = GenerationParams(
        caption="Instrumental jazz trio, warm acoustic piano, upright bass, brushed drums, relaxed swing, clear natural recording, no vocals.",
        lyrics="[Instrumental]", instrumental=True, bpm=100, **common,
    )
    if args.case == "vocal":
        params = GenerationParams(caption="Gentle acoustic pop, clear female lead singing in Portuguese, acoustic guitar, soft drums, warm intimate studio recording.",
            lyrics="[Verse]\nO vento leva a minha voz\nPor entre as ruas de cristal\nEu sigo a luz dentro de n\u00f3s\nAt\u00e9 chegar ao meu quintal", vocal_language="pt", **common)
    elif args.case in {"cover", "repaint"}:
        if not args.source:
            raise ValueError("Source required")
        params.task_type = args.case
        params.src_audio = args.source
        params.caption = "Instrumental bossa nova trio, nylon guitar, soft bass, brushed percussion, warm clear studio sound."
        params.audio_cover_strength = 0.75
        params.cover_noise_strength = 0.25
        if args.case == "repaint":
            params.repainting_start, params.repainting_end = 5, 12
    result = generate_music(handler, None, params, GenerationConfig(
        batch_size=1, use_random_seed=False, seeds=[42], audio_format="flac"),
        save_dir=str(REPORT / "music" / (args.model + "-" + args.case)))
    completed = time.perf_counter()
    data = asdict(result)
    if not result.success:
        raise RuntimeError(data)
    checks = []
    for audio in result.audios:
        path = audio.get("path") or audio.get("audio_path")
        samples, rate = sf.read(path)
        checks.append(dict(path=path, sample_rate=rate, seconds=len(samples)/rate,
                           finite=bool(np.isfinite(samples).all()), peak=float(np.abs(samples).max()),
                           rms=float(np.sqrt(np.mean(samples**2)))))
    data.update(model=args.model, case=args.case, load_seconds=loaded-start,
                generate_seconds=completed-loaded, total_seconds=completed-start,
                cuda_peak_mib=torch.cuda.max_memory_allocated()/1024**2, checks=checks)
    path = REPORT / (args.model + "-" + args.case + ".json")
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: data[key] for key in ("model", "case", "load_seconds", "generate_seconds", "checks")}), flush=True)


if __name__ == "__main__":
    main()
