"""Local A/B of new reference encodings, direct WAV conditioning and the active profile."""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from scipy.signal import resample_poly

from study_haru_dialogue import say
from test_haru_voice_reclones import RATE, ROOT, haru_voice, pcm, take, wait_for_voice_gpu


def download_f16(tmp):
    # Try HTTP ranges in parallel; validate the assembled file before using any weights.
    size = 10561406688
    chunk = 64 * 1024 * 1024
    url = ("https://huggingface.co/sakasegawa/Haru-4B-GGUF/resolve/"
           "fc026182f7bbfaa0400b2d44358a5e9e327b957f/Haru-4B-F16.gguf")
    target = tmp / "Haru-4B-F16.gguf"
    deadline = time.monotonic() + 660

    def fetch(start):
        if time.monotonic() >= deadline:
            raise TimeoutError("F16 download exceeded the time limit")
        end = min(size, start + chunk)
        path = tmp / f"range-{start}"
        response = subprocess.run(
            ["curl", "-fLsS", "--retry", "2", "--connect-timeout", "8", "--max-time", "45",
             "--max-filesize", str(end - start), "--range", f"{start}-{end - 1}",
             "--output", str(path), "--write-out", "%{http_code}", f"{url}?range_start={start}"],
            check=True, capture_output=True,
        )
        if response.stdout != b"206" or path.stat().st_size != end - start:
            raise RuntimeError("Incomplete F16 byte range")
        return path

    print("Downloading pinned F16 weights into a temporary directory", flush=True)
    sha = hashlib.sha256()
    with ThreadPoolExecutor(max_workers=12) as pool, target.open("wb") as output:
        jobs = [pool.submit(fetch, start) for start in range(0, size, chunk)]
        try:
            for idx, job in enumerate(jobs):
                path = job.result()
                data = path.read_bytes()
                output.write(data)
                sha.update(data)
                path.unlink()
                if idx % 16 == 15 or idx + 1 == len(jobs):
                    print(f"F16: {output.tell() / size:.0%}", flush=True)
        finally:
            for job in jobs:
                job.cancel()
    if sha.hexdigest() != "ea6caae8deccbf58f9b87dd11f893b13dfb96510357393994be94ce4258cc489":
        raise RuntimeError("F16 weight checksum did not match")
    return target


def encode(binary, weights, tmp, name, samples):
    wav, profile = tmp / f"{name}.wav", tmp / f"{name}.voice.gguf"
    sf.write(wav, samples, RATE, subtype="PCM_16")
    subprocess.run([binary, "voice", weights, wav, profile, "--device", "cpu", "--threads", "2"],
                   cwd=binary.parent, capture_output=True, check=True, timeout=60)
    return profile


async def main(tmp, args):
    binary, weights, current = haru_voice._prepare()
    if args.f16:
        weights = await asyncio.to_thread(download_f16, tmp)
    if args.local_f16:
        weights = args.local_f16.resolve()
        with weights.open("rb") as model:
            if hashlib.file_digest(model, "sha256").hexdigest() != "ea6caae8deccbf58f9b87dd11f893b13dfb96510357393994be94ce4258cc489":
                raise RuntimeError("F16 weight checksum did not match")
    await wait_for_voice_gpu(90 if args.f16 or args.local_f16 else 1)
    donor = args.reference
    raw, rate = sf.read(donor, always_2d=True)
    raw = resample_poly(raw.mean(axis=1), RATE, rate)
    profiles = {"current": current, "direct-wav": donor}
    if "raw-gguf" in args.profiles:
        profile = tmp / "raw-gguf.voice.gguf"
        subprocess.run([binary, "voice", weights, donor, profile, "--device", "cpu", "--threads", "2"],
                       cwd=binary.parent, capture_output=True, check=True, timeout=60)
        profiles["raw-gguf"] = profile
    for name, clip in {
        "short": raw[round(3.52 * RATE):round(8.84 * RATE)],
        "late": raw[round(10.01 * RATE):round(20.78 * RATE)],
        "trim-peaks": np.tanh(raw * 1.55)[round(0.28 * RATE):round(20.85 * RATE)] / 1.55,
        "headroom": raw * 0.8,
    }.items():
        if name in args.profiles:
            profiles[name] = encode(binary, weights, tmp, name, clip)
    profiles = {name: profiles[name] for name in args.profiles}
    for name, file in profiles.items():
        print(name, hashlib.sha256(file.read_bytes()).hexdigest(), flush=True)
    assets = [part for name, file in profiles.items() for part in ("--add-voice", f"{name}={file}")]
    snapshot = next((ROOT / "backend/data/cache/whisper/models/models--Systran--faster-whisper-base/snapshots").glob("*/model.bin"))
    recognizer = WhisperModel(str(snapshot.parent), device="cpu", cpu_threads=2, compute_type="int8", local_files_only=True)
    def recognize(samples):
        segments, _ = recognizer.transcribe(
            resample_poly(samples, 2, 3).astype(np.float32), language="pt",
            beam_size=3, condition_on_previous_text=False, vad_filter=True,
        )
        result = [(round(seg.start, 2), seg.text.strip()) for seg in segments]
        return (result[0][0], " ".join(text for _, text in result)) if result else (None, "")
    if args.holdout:
        fixtures = [(q, say(q, tmp)) for q in (
            "Qual é a capital do Brasil?", "Qual é a cor do céu num dia sem nuvens?",
            "Minha irmã se chama Rita. Como se chama a minha irmã?",
            "Eu perdi minhas chaves de casa. Onde eu posso procurar primeiro?",
        )]
        fixtures.append(("nome natural", pcm(ROOT / "logs/haru-question-0.wav")))
    else:
        fixtures = [(label, pcm(ROOT / "logs" / (fname + ".wav"))) for label, fname in (
            ("nome da Neve", "haru-question-0"), ("saudacao", "haru-question-1"),
            ("soma", "haru-question-2"), ("nome do usuario", "haru-quality-4"),
        )]
    proc = await asyncio.create_subprocess_exec(
        str(binary), "serve", str(weights), "--host", "127.0.0.1", "--port", "0", *assets,
        cwd=binary.parent, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        **({"creationflags": 0x08000000} if os.name == "nt" else {}))
    try:
        endpoint = await asyncio.wait_for(haru_voice._endpoint(proc), 120)
        for label, clip in fixtures:
            for lead in args.lead:
                start = round(RATE * lead)
                end = start + len(clip) // 2
                silence = bytes(start * 2)
                audio = silence + clip + bytes(RATE * 2 * 9)
                for voice in profiles:
                    treatments = (
                        [("automatic", {}), ("automatic-repeat", {}), ("fixed", {"seed": 987}),
                         ("cool", {"seed": 987, "temperature": 0.55}),
                         ("warm", {"seed": 987, "temperature": 0.85})]
                        if args.identity_matrix else [(str(seed), {"seed": seed}) for seed in args.seeds]
                    )
                    for treatment, overrides in treatments:
                        if args.treatments and treatment not in args.treatments:
                            continue
                        opts = dict(haru_voice._dialogue_options(RATE), voice=voice, **overrides)
                        if args.identity_matrix:
                            opts["name"] = "Neve"
                            if "seed" not in overrides:
                                opts.pop("seed", None)
                        if args.no_opening:
                            opts["speak_first"] = False  # Diagnostic only, not a user setting.
                        if args.short_card:
                            opts["persona"] = "Brasileira, numa conversa particular e informal. Fala uma frase curta e escuta a outra pessoa."
                        path = tmp / "reply.wav"
                        started = time.perf_counter()
                        result = await take(endpoint, opts, audio, lead, path)
                        elapsed = time.perf_counter() - started
                        output, _ = sf.read(path, dtype="float32")
                        delay, heard = recognize(output[end:])
                        print(json.dumps(dict(case=label, lead=lead, voice=voice,
                                              treatment=treatment, seed=opts.get("seed"), delay=delay,
                                              rtf=round(elapsed / (len(audio) / (2 * RATE)), 3),
                                              heard=heard, text=result["text"], pcm=result["pcm_sha256"])),
                              flush=True)
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
    if args.keep:
        assert args.keep_profile in profiles and args.keep_profile not in {"current", "direct-wav"}
        with args.keep.open("xb") as target:
            target.write(profiles[args.keep_profile].read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--profiles", nargs="+", default=["current", "direct-wav", "short", "late", "trim-peaks", "headroom"])
    parser.add_argument("--lead", nargs="+", type=float, default=[1.6])
    parser.add_argument("--seeds", nargs="+", type=int, default=[987])
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--no-opening", action="store_true")
    precision = parser.add_mutually_exclusive_group()
    precision.add_argument("--f16", action="store_true")
    precision.add_argument("--local-f16", type=Path)
    parser.add_argument("--short-card", action="store_true")
    parser.add_argument("--identity-matrix", action="store_true")
    parser.add_argument("--treatments", nargs="+")
    parser.add_argument("--keep", type=Path)
    parser.add_argument("--keep-profile")
    with tempfile.TemporaryDirectory(prefix="neve-haru-replies-") as work:
        asyncio.run(main(Path(work), parser.parse_args()))
