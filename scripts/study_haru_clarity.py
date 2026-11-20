"""Offline comparison of voice profiles. Requires a local Whisper cache and test speech."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from rapidfuzz.distance import Levenshtein
from scipy.signal import butter, resample_poly, sosfiltfilt

from study_haru_dialogue import say
from study_haru_timbre import pitches
from test_haru_voice_reclones import RATE, ROOT, haru_voice, pcm, shorten_pauses, take, wait_for_voice_gpu


def tokens(text):
    plain = unicodedata.normalize("NFKD", text.lower())
    return re.findall(r"[a-z0-9]+", "".join(c for c in plain if not unicodedata.combining(c)))


def encode(binary, weights, donor, directory, temp):
    source, rate = sf.read(donor, always_2d=True)
    ratio = gcd(rate, RATE)
    mono = resample_poly(source.mean(axis=1), RATE // ratio, rate // ratio)
    filtered = sosfiltfilt(butter(2, 75, btype="highpass", fs=RATE, output="sos"), mono)
    peak = lambda audio: audio * (0.81 / max(0.01, np.max(np.abs(audio))))
    variants = {
        "full": mono,
        "headroom": peak(mono),
        "pauses": shorten_pauses(mono),
        "filtered": peak(filtered),
        "front": peak(mono[round(0.25 * RATE):round(8.8 * RATE)]),
        "center": peak(mono[round(3.5 * RATE):round(13.4 * RATE)]),
        "tail": peak(mono[round(10.0 * RATE):round(20.7 * RATE)]),
        "ends": peak(np.r_[mono[round(0.25 * RATE):round(6.3 * RATE)], np.zeros(RATE // 5),
                            mono[round(15.0 * RATE):round(20.7 * RATE)]]),
    }
    for name, samples in variants.items():
        wav = temp / "reference.wav"
        sf.write(wav, np.clip(samples, -1, 1), RATE, subtype="PCM_16")
        subprocess.run(
            [str(binary), "voice", str(weights), str(wav), str(directory / f"{name}.voice.gguf"),
             "--device", "cpu", "--threads", "2"],
            cwd=binary.parent, check=True, capture_output=True, timeout=60,
        )


async def main(args, temp):
    binary, weights = haru_voice._prepare_runtime()
    if args.reference:
        args.candidates.mkdir(parents=True, exist_ok=False)
        encode(binary, weights, args.reference, args.candidates, temp)
    profiles = {"current": haru_voice.BUNDLED_VOICE_PROFILE}
    profiles.update({path.name.split(".")[0]: path for path in args.candidates.glob("*.voice.gguf")
                     if not args.only or path.name.split(".")[0] in args.only})
    print(json.dumps({"profiles": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                                   for name, path in profiles.items()}}), flush=True)
    assert len(profiles) > 1, "No candidate profile"
    snapshot = next((ROOT / "backend/data/cache/whisper/models/models--Systran--faster-whisper-base/snapshots").glob("*/model.bin"))
    asr = WhisperModel(str(snapshot.parent), device="cpu", cpu_threads=2, compute_type="int8", local_files_only=True)
    fixtures = [("opening", b"", 0, "pt")]
    if args.holdout:
        fixtures += [
            (name, say(message, temp), lead, "pt") for name, message, lead in (
                ("identity", "Bom dia. Como voc\u00ea se chama? Pode me dizer seu nome?", 6),
                ("memory", "Minha gata se chama Teresa. Qual \u00e9 o nome da minha gata?", 6),
                ("short", "Voc\u00ea prefere praia ou montanha?", 3),
            )
        ]
        fixtures += [("opening-en", b"", 0, "en")]
    else:
        fixtures += [
            (name, pcm(ROOT / "logs" / (file + ".wav")), lead, "pt")
            for name, file, lead in (("greeting", "haru-question-1", 6),
                                     ("question", "haru-question-0", 6), ("overlap", "haru-question-2", 2.5))
        ]
    await wait_for_voice_gpu(20)
    process = await asyncio.create_subprocess_exec(
        str(binary), "serve", str(weights), "--host", "127.0.0.1", "--port", "0",
        *[arg for name, path in profiles.items() for arg in ("--add-voice", f"{name}={path.resolve()}")],
        cwd=binary.parent, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        **({"creationflags": 0x08000000} if os.name == "nt" else {}),
    )
    try:
        endpoint = await asyncio.wait_for(haru_voice._endpoint(process), 120)
        for name in profiles:
            for case, speech, lead, language in fixtures:
                path = temp / "reply.wav"
                audio = bytes(round(lead * RATE) * 2) + speech + bytes(RATE * 2 * 11)
                options = dict(haru_voice._dialogue_options(RATE, language), voice=name)
                result = await take(endpoint, options, audio, lead, path)
                segments, _ = asr.transcribe(str(path), language=language, beam_size=3, vad_filter=True,
                                             word_timestamps=True, condition_on_previous_text=False)
                segments = list(segments)
                heard = " ".join(segment.text.strip() for segment in segments)
                spoken_duration = sum(segment.end - segment.start for segment in segments)
                after = lead + len(speech) / (RATE * 2)
                tail_words = [word for segment in segments for word in segment.words if speech and word.end > after]
                words = [word for segment in segments for word in segment.words]
                native, transcribed = tokens(result["text"]), tokens(heard)
                pitch = pitches(path)
                print(json.dumps({
                    "profile": name, "case": case, "native": result["text"], "heard": heard,
                    "native_words": len(native), "heard_words": len(transcribed),
                    "wer_vs_native": round(Levenshtein.distance(native, transcribed) / max(1, len(native)), 3),
                    "words_after_input": len(tail_words),
                    "word_confidence": round(float(np.mean([word.probability for word in words])), 3) if words else 0,
                    "words_per_second": round(len(transcribed) / spoken_duration, 2) if spoken_duration else 0,
                    "median_pitch": round(float(np.median(pitch))) if len(pitch) else None,
                }), flush=True)
    finally:
        if process.returncode is None:
            process.kill()
        await process.communicate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    args.candidates = args.candidates.resolve()
    with tempfile.TemporaryDirectory(prefix="neve-haru-clarity-") as directory:
        asyncio.run(main(args, Path(directory)))
