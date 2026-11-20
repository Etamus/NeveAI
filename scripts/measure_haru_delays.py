"""Compare Haru's native reply timing with the same PCM and voice profile."""

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np

from test_haru_voice_reclones import FRAME, RATE, haru_voice, pcm, take, wait_for_voice_gpu

STEP = FRAME / (RATE * 2)


def sound_blocks(samples):
    return np.max(np.abs(samples.astype(np.int32)), axis=1) > 500


async def measure(endpoint, options, audio, lead, out):
    start = time.perf_counter()
    report = await take(endpoint, options, audio, lead, out)
    elapsed = time.perf_counter() - start
    blocks = np.frombuffer(pcm(out), dtype="<i2").reshape(-1, FRAME // 2)
    return blocks, round(elapsed / (len(audio) / (2 * options["sample_rate"])), 3), report["text"]


CARDS = {
    "brief": "Seu nome \u00e9 Neve. Fala em portugu\u00eas brasileiro. Ouve a outra pessoa e responde ao que ela diz, em uma ou duas frases.",
    "private": "Seu nome \u00e9 Neve. Conversa particular em portugu\u00eas brasileiro entre duas pessoas. Cumprimente brevemente e escute.",
}


async def main(paths, biases, leads, card=None, holdout=False, max_silence_blocks=None, input_rate=RATE):
    await wait_for_voice_gpu(5)
    binary, weights, reference = await asyncio.to_thread(haru_voice._prepare)
    print(json.dumps({"profile_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(), "weights": weights.name}), flush=True)
    process = await asyncio.create_subprocess_exec(
        str(binary), "serve", str(weights), "--host", "127.0.0.1", "--port", "0",
        "--add-voice", f"neve={reference}", cwd=binary.parent,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        **({"creationflags": 0x08000000} if os.name == "nt" else {}),
    )
    try:
        endpoint = await asyncio.wait_for(haru_voice._endpoint(process), 120)
        with tempfile.TemporaryDirectory(prefix="neve-haru-latency-") as work:
            out = Path(work) / "reply.wav"
            fixtures = [(path.name, pcm(path)) for path in paths]
            if holdout:
                from study_haru_dialogue import say

                fixtures.extend((name, say(sentence, Path(work))) for name, sentence in (
                    ("capital", "Qual \u00e9 a capital do Brasil?"),
                    ("chaves", "Perdi as chaves de casa. Onde eu posso procurar primeiro?"),
                    ("memoria", "Minha amiga se chama Lara. Qual \u00e9 o nome da minha amiga?"),
                    ("cumprimento", "Boa tarde Neve, como vai voc\u00ea?"),
                ))
            if input_rate != RATE:
                from scipy.signal import resample_poly

                fixtures = [
                    (name, np.rint(np.clip(resample_poly(np.frombuffer(audio, dtype="<i2").astype(float),
                                                       input_rate // RATE, 1), -32768, 32767)).astype("<i2").tobytes())
                    for name, audio in fixtures
                ]
            scenarios = [(True, bias) for bias in biases] if biases is not None else [(False, 0.0), (True, 0.0)]
            for opening, bias in scenarios:
                options = dict(haru_voice._dialogue_options(input_rate), speak_first=opening, eop_bias=bias)
                if card:
                    options["persona"] = CARDS[card]
                baseline, _, _ = await measure(endpoint, options, bytes(input_rate * 2 * 24), 0, out)
                quiet_blocks = sound_blocks(baseline)
                silence_tail = int(quiet_blocks[int(6 / STEP):].sum())
                if max_silence_blocks is not None and silence_tail > max_silence_blocks:
                    print(json.dumps({"skipped_bias": bias, "output_on_silence_after_6s": silence_tail}), flush=True)
                    continue
                for name, utterance in fixtures:
                    for lead in leads:
                        prefix = bytes(round(lead * input_rate) * 2)
                        samples = np.frombuffer(utterance, dtype="<i2")
                        voiced_input = np.flatnonzero(np.abs(samples.astype(np.int32)) > 500)
                        first_voice = (len(prefix) // 2 + voiced_input[0]) / input_rate
                        last_voice = (len(prefix) // 2 + voiced_input[-1]) / input_rate
                        audio = prefix + utterance + bytes(input_rate * 2 * 10)
                        reply, factor, transcript = await measure(endpoint, options, audio, lead, out)
                        voiced = sound_blocks(reply)
                        different = np.any(reply != baseline[:len(reply)], axis=1)
                        times = np.arange(len(reply)) * STEP
                        affected = np.flatnonzero(voiced & different & (times >= last_voice))
                        first_run = next((i for i in affected if np.count_nonzero((affected >= i) & (affected < i + 5)) >= 3), None)
                        print(json.dumps({
                            "fixture": name, "opening": opening, "lead_s": lead, "eop_bias": bias, "input_rate": input_rate,
                            "first_distinct_audio_s": round(affected[0] * STEP - last_voice, 2) if len(affected) else None,
                            "first_sustained_audio_s": round(first_run * STEP - last_voice, 2) if first_run is not None else None,
                            "voiced_after": int(len(affected)),
                            "distinct_during_input": int(np.count_nonzero(voiced & different & (times >= first_voice) & (times < last_voice))),
                            "output_on_silence_after_6s": silence_tail,
                            "realtime_factor": factor, "native_text": transcript,
                        }), flush=True)
    finally:
        if process.returncode is None:
            process.kill()
        await process.communicate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("fixtures", type=Path, nargs="*")
    parser.add_argument("--biases", type=float, nargs="+")
    parser.add_argument("--leads", type=float, nargs="+", default=[2.5, 6])
    parser.add_argument("--card", choices=CARDS)
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--max-silence-blocks", type=int)
    parser.add_argument("--input-rate", type=int, choices=(RATE, RATE * 2), default=RATE)
    args = parser.parse_args()
    if not args.fixtures and not args.holdout:
        parser.error("provide voice fixtures or --holdout")
    asyncio.run(main(args.fixtures, args.biases, args.leads, args.card, args.holdout, args.max_silence_blocks, args.input_rate))
