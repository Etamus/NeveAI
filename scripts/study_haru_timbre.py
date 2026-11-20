"""Compare pitch stability and intelligibility on direct Haru output, with no microphone or UI."""

import asyncio
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from scipy.signal import find_peaks, resample_poly

from test_haru_voice_reclones import RATE, ROOT, haru_voice, pcm, take, wait_for_voice_gpu


def pitches(path):
    samples, rate = sf.read(path, always_2d=True)
    samples = resample_poly(samples.mean(axis=1), 8000, rate)
    result = []
    for start in range(0, len(samples) - 440, 160):
        frame = samples[start:start + 440]
        frame = frame - frame.mean()
        if np.sqrt(np.mean(frame**2)) < 0.008:
            continue
        corr = np.correlate(frame, frame, "full")[439:]
        corr = corr[:116] / (corr[0] * (1 - np.arange(116) / len(frame)))
        peaks, _ = find_peaks(corr[18:], height=0.66)
        if len(peaks):
            peaks = peaks + 18
            best = next(p for p in peaks if corr[p] >= 0.9 * max(corr[peaks]))
            result.append(8000 / best)
    return np.array(result)


async def main(tmp, extended, imported, donor):
    await wait_for_voice_gpu(1)
    binary, weights = haru_voice._prepare_runtime()
    ref = pitches(donor)
    low = np.quantile(ref, 0.25) * 0.72
    print(f"Reference pitch: median={np.median(ref):.0f} Hz; comparison threshold={low:.0f} Hz", flush=True)
    plain = tmp / "plain.voice.gguf"
    haru_voice._normalize_voice(donor, tmp / "plain.wav")
    subprocess.run([binary, "voice", weights, tmp / "plain.wav", plain, "--device", "cpu", "--threads", "2"],
                   cwd=binary.parent, capture_output=True, check=True, timeout=60)
    snapshot = next((ROOT / "backend/data/cache/whisper/models/models--Systran--faster-whisper-base/snapshots").glob("*/model.bin"))
    whisper = WhisperModel(str(snapshot.parent), device="cpu", cpu_threads=2, compute_type="int8", local_files_only=True)
    extra_voice = ["--add-voice", f"imported={imported.resolve()}"] if imported else []
    proc = await asyncio.create_subprocess_exec(
        str(binary), "serve", str(weights), "--host", "127.0.0.1", "--port", "0",
        "--add-voice", f"neve={haru_voice.BUNDLED_VOICE_PROFILE}", "--add-voice", f"plain={plain}", *extra_voice,
        cwd=binary.parent, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        **({"creationflags": 0x08000000} if os.name == "nt" else {}))
    try:
        endpoint = await asyncio.wait_for(haru_voice._endpoint(proc), 120)
        fixtures = [("abertura", "", 0, "pt"), ("abertura-en", "", 0, "en"),
                    ("cedo", "haru-question-0", 0.8, "pt"), ("depois", "haru-question-1", 3.2, "pt"),
                    ("nome", "haru-quality-4", 1.6, "pt")]
        if extended:
            fixtures = [("pausa-longa", "", 0, "pt"), ("quatro-turnos", "haru-question-0", 1.6, "pt")]
        for name, clip, lead, lang in fixtures:
            opts = dict(haru_voice._dialogue_options(RATE, language=lang), seed=987, speak_first=True)
            variants = {"atual": opts, "guia-175": dict(opts, guidance_scale=1.75),
                        "guia-190": dict(opts, guidance_scale=1.9),
                        "referencia-anterior": dict(opts, voice="plain"),
                        "uma-voz": dict(opts, situation=(
                            "A private phone call. Only Neve speaks for herself, in the same voice throughout."
                            if lang == "en" else "Ligacao privada. Neve fala por si mesma, sempre com a mesma voz."
                        ))}
            if extended:
                variants = {name: variants[name] for name in ("atual", "referencia-anterior")}
            if imported:
                variants = {"atual": opts, "importada": dict(opts, voice="imported")}
            for label, options in variants.items():
                path = tmp / "reply.wav"
                samples = bytes(round(lead * RATE) * 2)
                if clip:
                    samples += pcm(ROOT / "logs" / (clip + ".wav"))
                if extended and clip:
                    for filename in ("haru-question-1", "haru-quality-4", "haru-question-2"):
                        samples += bytes(8 * RATE * 2) + pcm(ROOT / "logs" / (filename + ".wav"))
                follow = 55 if extended and not clip else 11
                result = await take(endpoint, options, samples + bytes(follow * RATE * 2), lead, path)
                pitch = pitches(path)
                segments, _ = whisper.transcribe(str(path), language=lang, vad_filter=True,
                                                 condition_on_previous_text=False)
                print(json.dumps(dict(case=name, variant=label, frames=len(pitch),
                                      median=round(float(np.median(pitch))) if len(pitch) else None,
                                      low_pct=round(float(np.mean(pitch < low) * 100)) if len(pitch) else None,
                                      text=result["text"], heard=" ".join(part.text.strip() for part in segments))),
                      flush=True)
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--imported", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="neve-haru-timbre-") as folder:
        asyncio.run(main(Path(folder), args.extended, args.imported, args.reference))
