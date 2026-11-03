"""Read-only prompt audit and paired PT/EN generations, without changing app presets."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time

import httpx

from study_video_sweetspot import contact_sheet, fingerprint
from test_video_audio_live import inspect_video, monitor, require_idle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
OUTPUT = ROOT / 'logs/video-prompt-audit-20261102'
PROMPTS = {
    'vlog-original': 'Fa\u00e7a uma garota japonesa de cabelo rosa fazendo um vlog mostrando o rosto e conversando, falando "Hoje vamos falar sobre batata"',
    'vlog-adult': 'Fa\u00e7a uma mulher jovem adulta japonesa de cabelo rosa fazendo um vlog mostrando o rosto e conversando, falando "Hoje vamos falar sobre batata"',
    'vlog-short': 'Fa\u00e7a uma japonesa fazendo um vlog falando "Hoje vamos falar sobre batata"',
    'negative': 'Uma mulher de casaco amarelo caminha da direita para a esquerda numa praia ensolarada. '
    'N\u00e3o mostre outras pessoas, chuva ou texto.',
    'robot': 'Um rob\u00f4 pequeno com cabe\u00e7a de televis\u00e3o dan\u00e7a em uma cozinha, estilo desenho animado. Sem fala nem m\u00fasica.',
    'cars': 'Um carro vermelho permanece parado enquanto um carro azul passa por tr\u00e1s dele da esquerda para a direita.',
    'sign': 'Uma pessoa segura uma placa com o texto "ABERTO". N\u00e3o h\u00e1 falas.',
    'dialogue': 'Uma mulher diz em portugu\u00eas: "Bom dia!" Depois o homem responde: "Ol\u00e1!" N\u00e3o adicione outras falas.',
    'repeat': 'Uma mulher repete duas vezes: "Vamos come\u00e7ar". Sem outras pessoas.',
    'voiceover': 'Narra\u00e7\u00e3o em portugu\u00eas "Hoje \u00e9 um novo dia" enquanto a c\u00e2mera mostra uma montanha. N\u00e3o mostre pessoas.',
    'creative': 'Crie uma conversa breve em portugu\u00eas entre duas pessoas sobre jardinagem, sem texto na tela.',
    'reference': 'Anime a pessoa da imagem, preserve a roupa e o fundo, e fa\u00e7a ela sorrir.',
    'transition': 'Transi\u00e7\u00e3o cont\u00ednua da imagem 1 para a imagem 2, c\u00e2mera parada. Sem cortes e sem falas.',
    'knight-ir': 'integrated_multimodal_description: [Shot 1] A single continuous shot shows a knight '
    'under attack by a monster. A treasure chest forms the monster\'s entire head, connected directly '
    'to its neck. The chest itself occupies the head position and moves with the body throughout '
    'the attack. There is no additional human or animal face below the chest. Both the knight and '
    'the chest-headed monster remain visible.\n\noverall_soundscape: Nonverbal sounds of the attack.\n\n'
    'non_diegetic_music: None.',
    'knight-pt': 'Fa\u00e7a um cavaleiro sendo atacado por um monstro com cabe\u00e7a de ba\u00fa',
    'knight-en': 'Create a knight being attacked by a monster with a chest for a head.',
    'knight-en-clear': 'Create a knight being attacked by a monster whose head is a treasure chest.',
    'knight-pt-clear': 'Um monstro cuja pr\u00f3pria cabe\u00e7a \u00e9 um ba\u00fa ataca um cavaleiro.',
    'speech-pt': 'Fa\u00e7a v\u00e1rias garotas japonesas falando em portugu\u00eas "N\u00f3s te amamos Mateus"',
    'speech-en': 'Create several Japanese girls speaking in Portuguese: "N\u00f3s te amamos Mateus".',
    'speech-en-tags': 'Several Japanese girls speak Portuguese and say: <d>[Portuguese] N\u00f3s te amamos Mateus</d>.',
    'control-pt': 'Um cubo azul \u00e0 esquerda de uma esfera vermelha sobre uma mesa branca. '
    'A esfera vermelha rola da direita para a esquerda em dire\u00e7\u00e3o ao cubo azul. '
    'C\u00e2mera fixa, sem cortes. Sem fala ou m\u00fasica.',
    'control-en': 'A blue cube to the left of a red sphere on a white table. '
    'The red sphere rolls from right to left toward the blue cube. '
    'Fixed camera, no cuts. No speech or music.',
}


async def collect():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8080', timeout=60) as client:
        response = await client.get('/api/v1/files/generated', params={'kind': 'video', 'limit': 12})
        response.raise_for_status()
        rows = []
        for item in response.json():
            data = item.get('meta', {}).get('data', {})
            row = dict(id=item['id'], created=item.get('created_at'), **data)
            rows.append(row)
            print('SAVED PROMPT', json.dumps(row, ensure_ascii=True), flush=True)
            if data.get('prompt') == PROMPTS['knight-pt']:
                media = await client.get(f"/api/v1/files/{item['id']}/content")
                media.raise_for_status()
                path = OUTPUT / f"original-{item['id']}.mp4"
                path.write_bytes(media.content)
                await asyncio.to_thread(contact_sheet, path)
        (OUTPUT / 'saved-prompts.json').write_text(json.dumps(rows, indent=2), encoding='utf8')


async def main(args):
    from neveai.routers.video_generation import minimax_h3_runtime
    from neveai.routers.video_quality_generation import video15_runtime
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.analyze:
        from PIL import Image, ImageDraw
        import av
        import numpy as np
        from transformers import Qwen2Tokenizer
        tokenizer = Qwen2Tokenizer.from_pretrained(str(ROOT / 'backend/data/cache/video_generation/ComfyUI/comfy/text_encoders/qwen25_tokenizer'), local_files_only=True)
        tokens = {}
        for key, prompt in PROMPTS.items():
            ids = tokenizer(prompt, add_special_tokens=False)['input_ids']
            decoded = tokenizer.decode(ids)
            assert decoded == prompt, (key, decoded)
            tokens[key] = dict(count=len(ids), exact_roundtrip=True, ids=ids)
        tokens['dialogue_tag'] = tokenizer('<d>[Portuguese] N\u00f3s te amamos Mateus</d>', add_special_tokens=False)['input_ids']
        (OUTPUT / 'token-audit.json').write_text(json.dumps(tokens, indent=2), encoding='utf8')
        for path in OUTPUT.glob('*.mp4'):
            with av.open(str(path)) as video:
                frames = [frame.to_image() for frame in video.decode(video=0)]
            indices = np.linspace(0, len(frames)-1, 12, dtype=int)
            sheet = Image.new('RGB', (432*3, 270*4), '#222222')
            draw = ImageDraw.Draw(sheet)
            for cell, index in enumerate(indices):
                frame = frames[index]
                frame.thumbnail((432, 240))
                x, y = (cell%3)*432, (cell//3)*270
                sheet.paste(frame, (x, y+25))
                draw.text((x+5, y+5), f'{path.stem} frame {index}', fill='white')
            sheet.save(path.with_suffix('.timeline.jpg'), quality=95)
        from faster_whisper import WhisperModel
        snapshots = ROOT / 'backend/data/cache/whisper/models/models--Systran--faster-whisper-base/snapshots'
        model_path = next(path for path in snapshots.iterdir() if (path/'model.bin').is_file())
        recognizer = WhisperModel(str(model_path), device='cpu', compute_type='int8', cpu_threads=2, local_files_only=True)
        speech = []
        for path in sorted(OUTPUT.glob('*.mp4')):
            if not any(tag in path.stem for tag in ('speech', 'vlog')):
                continue
            segments, info = recognizer.transcribe(str(path), beam_size=5, condition_on_previous_text=False, vad_filter=False)
            row = dict(case=path.stem, language=info.language, probability=info.language_probability,
                       text=' '.join(segment.text.strip() for segment in segments))
            segments, _ = recognizer.transcribe(str(path), language='pt', beam_size=5,
                                                condition_on_previous_text=False, vad_filter=False)
            row['forced_portuguese_text'] = ' '.join(segment.text.strip() for segment in segments)
            speech.append(row)
        (OUTPUT/'speech-diagnostic.json').write_text(json.dumps(speech, indent=2), encoding='utf8')
        print(json.dumps(speech, ensure_ascii=True), flush=True)
        return
    await require_idle()
    if args.collect:
        await collect()
    (OUTPUT / 'prompt-pairs.json').write_text(json.dumps(PROMPTS, indent=2), encoding='utf8')
    for model, scene in (case.split(':') for case in args.case):
        runtime = minimax_h3_runtime if model == 'h3' else video15_runtime
        path = OUTPUT / f'{model}-{scene}-seed{args.seed}.mp4'
        if path.exists():
            print('SKIP', path.name, flush=True)
            continue
        await require_idle()
        started = time.perf_counter()
        events, gpu = [], []

        async def progress(description, value=None):
            events.append(dict(seconds=time.perf_counter()-started, description=description, progress=value))
            print(path.stem, round(events[-1]['seconds'], 1), description, value, flush=True)

        prompt = PROMPTS[scene]
        graph = runtime._build_workflow(prompt, args.seed, None, width=864, height=480, frames=124)
        assert graph['4']['inputs']['prompt'] == prompt
        sampler = asyncio.create_task(monitor(gpu))
        try:
            await runtime.prepare(progress)
            result = await runtime._generate_once(prompt, progress, width=864, height=480,
                                                  frames=124, seed=args.seed)
            elapsed = time.perf_counter()-started
            path.write_bytes(result['video'])
            inspection = await asyncio.to_thread(inspect_video, path)
            await asyncio.to_thread(contact_sheet, path)
            row = dict(model=model, scene=scene, seed=args.seed, prompt=prompt, seconds=elapsed,
                       workflow_prompt=graph['4']['inputs']['prompt'],
                       prompt_sha256=hashlib.sha256(prompt.encode('utf8')).hexdigest(),
                       inspection=inspection, video_sha256=await asyncio.to_thread(fingerprint, path),
                       gpu=gpu, events=events, worker_log=list(runtime._log_tail))
            path.with_suffix('.json').write_text(json.dumps(row, indent=2), encoding='utf8')
            print('PASS', path.stem, elapsed, flush=True)
        finally:
            sampler.cancel()
            try:
                await sampler
            except asyncio.CancelledError:
                pass
            await runtime.stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--analyze', action='store_true')
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--seed', type=int, default=12345)
    asyncio.run(main(parser.parse_args()))
