"""Compare local reference profiles with the same model, seed and spoken fixtures."""

import asyncio
import argparse
import os
import subprocess
import wave
from pathlib import Path

import soundfile as sf
import numpy as np
from scipy import signal

from test_haru_voice_turn import ROOT, haru_voice, probe


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--cleaned", action="store_true")
    args = parser.parse_args()
    output = ROOT / "logs/haru-reference-study"
    output.mkdir(exist_ok=True)
    binary, weights = await asyncio.to_thread(haru_voice._prepare_runtime)
    audio, rate = sf.read(args.reference)
    profiles = {"baseline": haru_voice.BUNDLED_VOICE_PROFILE}
    clips = [(label, audio[int(start * rate):int(end * rate)], rate) for label, start, end in [
        ("full", 0, len(audio) / rate),
        ("phrase-a", 3.52, 8.84),
        ("phrase-b", 11.7, 15.58),
        ("phrase-c", 15.8, 20.78),
        ("last-section", 10.01, 20.78),
    ]]
    if args.cleaned:
        filtered = signal.sosfiltfilt(signal.butter(2, 65, "highpass", fs=rate, output="sos"), audio)
        clips = [
            ("downsample", signal.resample_poly(audio, 1, 2), rate // 2),
            ("headroom", audio * 0.82, rate),
            ("filtered", filtered * (0.93 / max(abs(filtered))), rate),
            ("short-pause", np.concatenate((audio[:int(9.07 * rate)], audio[int(9.75 * rate):])), rate),
        ]
    for label, samples, sample_rate in clips:
        wav = output / f"{label}.wav"
        model = output / f"{label}.voice.gguf"
        sf.write(wav, samples, sample_rate, subtype="PCM_16")
        subprocess.run([str(binary), "voice", str(weights), str(wav), str(model), "--device", "cpu",
                        "--threads", "2"], cwd=binary.parent, check=True, timeout=60)
        profiles[label] = model
    if "full" in profiles:
        print("Full reference exactly matches bundled profile:",
              profiles["full"].read_bytes() == profiles["baseline"].read_bytes(), flush=True)
    presets = [part for label, path in profiles.items() for part in ("--add-voice", f"{label}={path}")]
    proc = await asyncio.create_subprocess_exec(
        str(binary), "serve", str(weights), "--host", "127.0.0.1", "--port", "0", *presets,
        cwd=binary.parent, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        **({"creationflags": 0x08000000} if os.name == "nt" else {}),
    )
    try:
        endpoint = await asyncio.wait_for(haru_voice._endpoint(proc), 120)
        for filename in ("haru-question-0.wav", "haru-question-1.wav", "haru-quality-4.wav", "haru-question-2.wav"):
            with wave.open(str(ROOT / "logs" / filename), "rb") as wav:
                assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (24000, 1, 2)
                frames = bytes(48000) + wav.readframes(wav.getnframes()) + bytes(288000)
            for name in profiles:
                voiced, transcript = await probe(endpoint, frames, dict(haru_voice._dialogue_options(24000), voice=name, speak_first=False))
                print(filename, name, voiced, repr(transcript), flush=True)
        for name in profiles:
            voiced, transcript = await probe(endpoint, bytes(6 * 48000),
                                             dict(haru_voice._dialogue_options(24000), voice=name, speak_first=True))
            print("spontaneous", name, voiced, repr(transcript), flush=True)
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()


if __name__ == "__main__":
    asyncio.run(main())
