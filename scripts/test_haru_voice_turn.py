"""Measure replies to WAV prompts (24 kHz PCM16 mono) using the actual GPU runtime."""

import argparse
import asyncio
import json
import os
import sys
import wave
from pathlib import Path

from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.routers import haru_voice


async def probe(endpoint, audio, options):
    async with connect(endpoint, proxy=None) as ws:
        await ws.send(json.dumps(options))
        started = json.loads(await ws.recv())
        assert started["type"] == "started", started
        first = await ws.recv()
        if isinstance(first, str):
            assert json.loads(first)["type"] == "text", first
            first = await ws.recv()
        assert len(first) == 6400
        answer = []
        audible = 0
        for offset in range(0, len(audio), 6400):
            await ws.send(audio[offset:offset+6400].ljust(6400, b"\0"))
            response = await asyncio.wait_for(ws.recv(), 10)
            if isinstance(response, str):
                text = json.loads(response)
                assert text["type"] == "text", text
                answer.append(text["text"])
                response = await asyncio.wait_for(ws.recv(), 10)
            if offset >= len(audio) - 24000 * 2 * 6 and any(
                abs(int.from_bytes(response[i:i+2], "little", signed=True)) > 500
                for i in range(0, len(response), 2)
            ):
                audible += 1
        return audible, "".join(answer)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", nargs="+", type=Path)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--seeds", nargs="+", type=int, default=(112, 1, 14, 42, 1337))
    parser.add_argument("--persona")
    parser.add_argument("--backchannel", choices=("low", "mid", "high"))
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--quality-matrix", action="store_true")
    parser.add_argument("--introduction-matrix", action="store_true")
    args = parser.parse_args()
    binary, weights, reference = await asyncio.to_thread(haru_voice._prepare)
    proc = await asyncio.create_subprocess_exec(
        str(binary), "serve", str(weights), "--host", "127.0.0.1", "--port", "0",
        "--add-voice", f"neve={reference}", cwd=binary.parent,
        stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        **({"creationflags": 0x08000000} if os.name == "nt" else {}),
    )
    try:
        endpoint = await asyncio.wait_for(haru_voice._endpoint(proc), 120)
        candidates = dict(haru_voice._dialogue_options(24000), speak_first=False)
        seeds = args.seeds
        for path in args.wav:
            with wave.open(str(path), "rb") as recording:
                assert (recording.getframerate(), recording.getnchannels(), recording.getsampwidth()) == (24000, 1, 2)
                clip = recording.readframes(recording.getnframes())
            clip = bytes(24000 * 2) + clip + bytes(24000 * 2 * 6)
            base = candidates.copy()
            if args.persona:
                base["persona"] = args.persona
            if args.backchannel:
                base["backchannel"] = args.backchannel
            options = [base]
            if args.compare:
                options = [{**base, "seed": seed, "temperature": 0.7} for seed in seeds]
            if args.quality_matrix:
                options = [
                    base,
                    {**base, "temperature": 0.6},
                    {**base, "top_k": 12},
                    {**base, "situation": "Conversa privada entre duas pessoas. Pergunte quando nao entender. Nao invente assuntos ou fatos."},
                    {**base, "persona": "Fala em portugu\u00eas brasileiro, com clareza e naturalidade."},
                    {**base, "persona": "Conversa em portugu\u00eas brasileiro. S\u00f3 se apresenta se perguntarem seu nome."},
                ]
            if args.introduction_matrix:
                brief = {**base, "persona": "Fala em portugu\u00eas brasileiro, com clareza e naturalidade."}
                options = [base, {**brief, "eop_bias": 0.5}, {**brief, "eop_bias": 1.0},
                           {**brief, "situation": "Conversa particular, sem plateia nem apresentacao."},
                           {**base, "persona": "Seu nome \u00e9 Neve. Fala em portugu\u00eas brasileiro, com clareza e naturalidade."}]
            keep = []
            for i, entry in enumerate(options):
                audible, answer = await probe(endpoint, clip, entry)
                print(path.name, i, entry["seed"], entry["temperature"], audible, repr(answer), flush=True)
                if not args.compare and not args.quality_matrix and not args.introduction_matrix:
                    assert audible >= 5 and answer.strip(), "No spoken reply to a real utterance"
                if audible >= 5 and answer.strip():
                    keep.append(entry["seed"])
            if args.qualify:
                seeds = keep
                if not seeds:
                    break
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()


if __name__ == "__main__":
    asyncio.run(main())
