"""Opt-in comparison of private reference candidates, without replacing the default."""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import wave
from math import gcd
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf
from scipy import signal
from websockets.asyncio.client import connect

from test_haru_voice_turn import ROOT, haru_voice


RATE = 24000
FRAME = 6400


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pcm(path):
    with wave.open(str(path), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (RATE, 1, 2), path
        return wav.readframes(wav.getnframes())


def shorten_pauses(samples):
    step = RATE // 50
    count = len(samples) // step
    chunks = samples[:count * step].reshape(count, step)
    quiet = np.sqrt(np.mean(chunks**2, axis=1)) < 0.004
    intervals = np.flatnonzero(np.diff(np.r_[False, quiet, False]))
    keep = np.ones(len(samples), dtype=bool)
    for start, end in zip(intervals[::2], intervals[1::2]):
        if end - start >= 20:
            keep[(start + 6) * step:(end - 6) * step] = False
    return samples[keep]


def leveling_settings(samples):
    from scipy.ndimage import gaussian_filter1d

    step = RATE // 20
    count = len(samples) // step
    rms = np.sqrt(np.mean(samples[:count * step].reshape(count, step)**2, axis=1))
    envelope = gaussian_filter1d(rms, sigma=5)
    target = np.median(envelope[envelope > 0.012])
    gain = np.clip((target / np.maximum(envelope, 0.012))**0.35, 0.75, 1.3)
    leveled = samples * np.interp(np.arange(len(samples)), (np.arange(count) + 0.5) * step, gain)

    def peak_limit(audio):
        return audio * min(1.0, 0.9 / max(abs(audio)))

    def boundary(position):
        index = round(position * count)
        start = max(1, index - 10)
        end = min(count - 1, index + 11)
        return (start + np.argmin(rms[start:end])) * step

    return {
        "gentle-level": peak_limit(leveled),
        "soft-peak": np.tanh(samples * 1.55) / 1.55,
        "clean-front": samples[:boundary(0.86)],
        "clean-center": samples[boundary(0.14):boundary(0.86)],
    }


async def wait_for_voice_gpu(timeout):
    busy_names = {"speech", "speech.exe", "llama-server", "llama-server.exe"}
    deadline = time.monotonic() + timeout
    while any((p.info["name"] or "").lower() in busy_names for p in psutil.process_iter(["name"])):
        if time.monotonic() >= deadline:
            raise RuntimeError("Voice or chat was still using the local runtime")
        await asyncio.sleep(2)


async def take(endpoint, options, audio, lead, output):
    spoken_pcm = []
    text = []
    input_frame = FRAME * options["sample_rate"] // RATE
    async with connect(endpoint, proxy=None) as ws:
        await ws.send(json.dumps(options))
        assert json.loads(await ws.recv())["type"] == "started"

        async def receive():
            while True:
                packet = await asyncio.wait_for(ws.recv(), 12)
                if isinstance(packet, bytes):
                    assert len(packet) == FRAME
                    return packet
                event = json.loads(packet)
                assert event["type"] == "text", event
                text.append(event["text"])

        if input_frame == FRAME:
            spoken_pcm.append(await receive())
            for offset in range(0, len(audio), input_frame):
                await ws.send(audio[offset:offset + input_frame].ljust(input_frame, b"\0"))
                spoken_pcm.append(await receive())
        else:
            # Resampling needs lookahead; the server does not reply once per input packet.
            packet_size = options["sample_rate"] * 2 * 40 // 1000
            count = (len(audio) + input_frame - 1) // input_frame + 1

            async def send():
                padded = audio + bytes(input_frame * 2)
                for offset in range(0, len(padded), packet_size):
                    await ws.send(padded[offset:offset + packet_size])
                    await asyncio.sleep(0)

            sender = asyncio.create_task(send())
            try:
                for _ in range(count):
                    spoken_pcm.append(await receive())
            finally:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)

    rendered = b"".join(spoken_pcm)
    all_pcm = np.frombuffer(rendered, dtype="<i2").reshape(-1, FRAME // 2)
    audible = np.max(np.abs(all_pcm.astype(np.int32)), axis=1) > 500
    prefix_count = int(lead * RATE * 2 / FRAME)
    with wave.open(str(output), "wb") as wav:
        wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        wav.writeframes(rendered)
    return {
        "audible_frames": int(audible[prefix_count:].sum()),
        "before_input_frames": int(audible[:prefix_count].sum()),
        "pcm_sha256": hashlib.sha256(rendered).hexdigest(),
        "text": "".join(text),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path, nargs="+")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=haru_voice.BUNDLED_VOICE_PROFILE)
    parser.add_argument("--leveling", action="store_true")
    parser.add_argument("--english", type=Path)
    parser.add_argument("--wait-for-idle", type=int, default=0)
    args = parser.parse_args()
    output = Path(tempfile.mkdtemp(prefix="haru-reclones-", dir=ROOT / "logs"))
    current = args.baseline
    before = digest(current)
    saved = output / "current-backup.voice.gguf"
    shutil.copy2(current, saved)
    print("Results folder:", output, flush=True)
    binary, weights = await asyncio.to_thread(haru_voice._prepare_runtime)
    profiles = {"current": saved}
    reference, rate = sf.read(args.reference, always_2d=True)
    divisor = gcd(rate, RATE)
    normal = signal.resample_poly(reference.mean(axis=1), RATE // divisor, rate // divisor)
    clean = signal.sosfiltfilt(signal.butter(2, (75, 8000), btype="bandpass", fs=RATE, output="sos"), normal)
    settings = leveling_settings(normal) if args.leveling else {
        "headroom": normal * (0.71 / max(abs(normal))),
        "short-pauses": shorten_pauses(normal),
        "bandpass": clean,
        "reference-tail": normal[round(len(normal) * 0.12):],
    }
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        if not args.leveling:
            profiles["reimport"] = output / "reimport.voice.gguf"
            await asyncio.to_thread(haru_voice._import_profile, args.reference, profiles["reimport"])
        for name, audio in settings.items():
            sample = Path(tmp) / f"{name}.wav"
            sf.write(sample, np.clip(audio, -1, 1), RATE, subtype="PCM_16")
            profiles[name] = output / f"{name}.voice.gguf"
            await asyncio.to_thread(
                subprocess.run, [str(binary), "voice", str(weights), str(sample), str(profiles[name]),
                                 "--device", "cpu", "--threads", "2"],
                cwd=binary.parent, check=True, capture_output=True, timeout=60,
            )

    hashes = {name: digest(path) for name, path in profiles.items()}
    unique = {}
    for name, sha in hashes.items():
        unique.setdefault(sha, name)
    voices = [item for name in unique.values() for item in ("--add-voice", f"{name}={profiles[name]}")]
    if args.wait_for_idle:
        await wait_for_voice_gpu(args.wait_for_idle)
    child = await asyncio.create_subprocess_exec(
        str(binary), "serve", str(weights), "--host", "127.0.0.1", "--port", "0", *voices,
        cwd=binary.parent, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        **({"creationflags": 0x08000000} if os.name == "nt" else {}),
    )
    results = []
    try:
        endpoint = await asyncio.wait_for(haru_voice._endpoint(child), 120)
        cases = [(path.stem, pcm(path), 1.0, False) for path in args.wav]
        cases += [("first-question-later", pcm(args.wav[0]), 4.0, False),
                  ("spontaneous", b"", 0.0, True)]
        if args.english:
            cases.append(("english", pcm(args.english), 1.0, False))
        for name in unique.values():
            for case, voice, lead, spontaneous in cases:
                language = "en" if case == "english" else "pt"
                options = dict(haru_voice._dialogue_options(RATE, language), voice=name, seed=987, speak_first=spontaneous)
                input_pcm = bytes(round(RATE * 2 * lead)) + voice + bytes(RATE * 2 * 7)
                result = await take(endpoint, options, input_pcm, lead, output / f"{name}-{case}.wav")
                results.append({"profile": name, "case": case, "lead_seconds": lead, **result})
                print(name, case, result["audible_frames"], result["before_input_frames"], repr(result["text"]), flush=True)
        first = results[0]
        repeat = await take(
            endpoint, dict(haru_voice._dialogue_options(RATE), voice="current", seed=987, speak_first=False),
            bytes(RATE * 2) + pcm(args.wav[0]) + bytes(RATE * 2 * 7), 1.0, output / "current-repeat.wav",
        )
        identical = first["pcm_sha256"] == repeat["pcm_sha256"]
        report = {"profile_sha256": hashes, "repeat_pcm_identical": identical, "results": results}
        (output / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Current profile repeated identical PCM:", identical, flush=True)
    finally:
        if child.returncode is None:
            child.kill()
        await child.communicate()
        assert digest(current) == before == digest(saved), "Default voice was unexpectedly modified"


if __name__ == "__main__":
    asyncio.run(main())
