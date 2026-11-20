"""Opt-in Portuguese speech regression study. Keep all recordings and profiles temporary."""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from scipy.signal import resample_poly
from websockets.asyncio.client import connect

from test_haru_voice_reclones import RATE, ROOT, haru_voice, pcm, take, wait_for_voice_gpu


def through_bridge(packets, count):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(haru_voice.router)
    fake_user = AsyncMock(return_value=SimpleNamespace(role="user", id="haru-local-study"))
    runtime_defaults = haru_voice._dialogue_options
    with patch.object(haru_voice, "get_current_user", new=fake_user), \
         patch.object(haru_voice, "_dialogue_options", lambda *args: dict(runtime_defaults(*args), seed=987)), \
         TestClient(app) as client:
        with client.websocket_connect("/voice", headers={"origin": "http://testserver"}) as ws:
            ws.send_json({"sample_rate": 48000, "language": "pt"})
            assert ws.receive_json()["type"] == "preparing"
            assert ws.receive_json()["type"] == "started"
            def send():
                for packet in packets:
                    ws.send_bytes(packet)
                    time.sleep(0.04)
            with ThreadPoolExecutor(max_workers=1) as pool:
                sender = pool.submit(send)
                frames = [ws.receive_bytes() for _ in range(count)]
                sender.result()
                return frames


async def transport(endpoint, packets):
    # 10 x 40 ms microphone packets produce 3 x 133 ms model frames.
    count = len(packets) * 3 // 10 - 1
    async with connect(endpoint, proxy=None) as ws:
        await ws.send(json.dumps(dict(haru_voice._dialogue_options(48000), seed=987)))
        assert json.loads(await ws.recv())["type"] == "started"
        async def send():
            for packet in packets:
                await ws.send(packet)
                await asyncio.sleep(0.04)
        sender = asyncio.create_task(send())
        direct = []
        try:
            while len(direct) < count:
                packet = await asyncio.wait_for(ws.recv(), 12)
                if isinstance(packet, bytes):
                    direct.append(packet)
                else:
                    assert json.loads(packet)["type"] == "text", packet
            await sender
        finally:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
    return direct


def say(text, tmp):
    import win32com.client

    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voice.Voice = voice.GetVoices("Language=416").Item(0)
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Format.Type = 22  # mono PCM16, 22.05 kHz
    stream.Open(str(tmp / "question.wav"), 3, False)
    try:
        voice.AudioOutputStream = stream
        voice.Speak(text)
    finally:
        stream.Close()
    samples, rate = sf.read(tmp / "question.wav")
    return np.rint(np.clip(resample_poly(samples, RATE, rate), -1, 1) * 32767).astype("<i2").tobytes()


async def study(tmp, args):
    await wait_for_voice_gpu(1)
    binary, weights, reference = haru_voice._prepare()
    plain = tmp / "plain.voice.gguf"
    haru_voice._normalize_voice(args.reference, tmp / "plain.wav")
    subprocess.run([binary, "voice", weights, tmp / "plain.wav", plain, "--device", "cpu", "--threads", "2"],
                   cwd=binary.parent, capture_output=True, check=True, timeout=60)
    sentences = [
        "Quantas rodas tem uma bicicleta comum?",
        "Meu nome é Ana. Qual é o meu nome?",
        "Me diga uma fruta amarela, só uma.",
        "Qual é a capital do Brasil?",
        "Eu perdi minhas chaves. Onde você sugere procurar primeiro?",
        "Quanto é dois mais dois?",
    ]
    prompts = [(q, say(q, tmp)) for q in sentences]
    prompts.append(("dois turnos", say("Minha irmã se chama Rita.", tmp) + bytes(6 * RATE * 2)
                    + say("Como se chama minha irmã?", tmp)))
    prompts.append(("controle gravado", pcm(ROOT / "logs/haru-quality-4.wav")))
    snapshot = next((ROOT / "backend/data/cache/whisper/models/models--Systran--faster-whisper-base/snapshots").glob("*/model.bin"))
    asr = WhisperModel(str(snapshot.parent), device="cpu", cpu_threads=2, compute_type="int8", local_files_only=True)
    def transcript(path):
        parts, _ = asr.transcribe(str(path), beam_size=3, language="pt", condition_on_previous_text=False, vad_filter=True)
        return " ".join(p.text.strip() for p in parts)
    current = dict(haru_voice._dialogue_options(RATE), seed=987, speak_first=False)
    concise = dict(current, persona="Neve é uma assistente brasileira. Ouve a pergunta e responde diretamente em uma ou duas frases curtas.")
    settings = {
        "original": current,
        "breve": concise,
        "dialogo": dict(concise, situation="Conversa individual. A outra pessoa faz uma pergunta e aguarda uma resposta breve.", backchannel="low"),
        "voz-anterior": dict(current, voice="plain"),
        "sem-clone": {k: v for k, v in current.items() if k != "voice"},
        "escuta": dict(current, persona="Boa ouvinte, responde em português com poucas palavras e depois escuta.",
                       temperature=0.5, situation="Duas pessoas conversam por telefone.", eop_bias=1.0),
        "escuta-seed": dict(current, persona="Boa ouvinte, responde em português com poucas palavras e depois escuta.",
                            temperature=0.5, situation="Duas pessoas conversam por telefone.", eop_bias=1.0, seed=42),
    }
    proc = await asyncio.create_subprocess_exec(
        str(binary), "serve", str(weights), "--host", "127.0.0.1", "--port", "0",
        "--add-voice", f"neve={reference}", "--add-voice", f"plain={plain}", cwd=binary.parent,
        stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        **({"creationflags": 0x08000000} if os.name == "nt" else {}))
    try:
        endpoint = await asyncio.wait_for(haru_voice._endpoint(proc), 120)
        if args.bridge:
            raw = np.frombuffer(prompts[-1][1], dtype="<i2").astype(float)
            doubled = np.rint(resample_poly(raw, 2, 1)).clip(-32768, 32767).astype("<i2").tobytes()
            raw = bytes(96000) + doubled + bytes(96000 * 8)
            packets = [raw[i:i+3840] for i in range(0, len(raw) // 38400 * 38400, 3840)]
            direct = await transport(endpoint, packets)
            # Release all GPU resources before testing the application's own process.
            proc.kill()
            await proc.communicate()
            bridged = await asyncio.to_thread(through_bridge, packets, len(direct))
            ref, observed = (b"".join(stream) for stream in (direct, bridged))
            assert len(ref) and np.max(np.abs(np.frombuffer(ref, dtype="<i2").astype(int))) > 500
            assert observed == ref, "Bridge audio differed from the native runtime"
            print("PASS: bridge and native playback identical from the opening:", len(ref), hashlib.sha256(ref).hexdigest())
            return
        for i, (label, clip) in enumerate(prompts):
            if not args.start <= i < args.end:
                continue
            sf.write(tmp / "input.wav", np.frombuffer(clip, dtype="<i2"), RATE, subtype="PCM_16")
            print(json.dumps({"question": label, "asr_input": transcript(tmp / "input.wav")}), flush=True)
            for setting in args.settings:
                rendered = tmp / "reply.wav"
                audio = bytes(round(args.lead * RATE) * 2) + clip + bytes(12 * RATE * 2)
                result = await take(endpoint, settings[setting], audio, args.lead, rendered)
                print(json.dumps(dict(case=label, setting=setting, internal=result["text"],
                                      audible_frames=result["audible_frames"], spoken=transcript(rendered)),
                                 ensure_ascii=True), flush=True)
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--settings", nargs="+", default=["original", "breve", "dialogo", "voz-anterior"])
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=8)
    parser.add_argument("--lead", type=float, default=1)
    parser.add_argument("--bridge", action="store_true")
    with tempfile.TemporaryDirectory() as work:
        asyncio.run(study(Path(work), parser.parse_args()))
