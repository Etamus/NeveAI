"""Opt-in local inference smoke test; creates no chats or files in the library."""
import json
import time
from pathlib import Path

import httpx

BASE = 'http://127.0.0.1:8080'
ROOT = Path(__file__).resolve().parents[1]
with httpx.Client(timeout=180) as client:
    available = client.get(BASE + '/llamacpp/models').json()['models']
    if any(model['is_loaded'] for model in available):
        raise RuntimeError('Test requires an idle runtime with no model loaded')
    chosen = min(available, key=lambda model: model['file_size'])
    model_id = chosen['id']
    loaded = False
    try:
        response = client.post(BASE + '/llamacpp/models/load', json={
            'filename': chosen['filename'], 'n_ctx': 4096, 'n_gpu_layers': -1,
        })
        response.raise_for_status()
        loaded = True
        started = time.monotonic()
        measurements, content = [], []
        with client.stream('POST', BASE + '/llamacpp/chat/completions', json={
            'model': model_id, 'messages': [{'role':'user','content':'List the numbers from 1 to 60, one number per line. Start immediately.'}],
            'stream':True, 'max_tokens':128, 'temperature':0,
        }) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith('data: ') or line[6:] == '[DONE]':
                    continue
                event = json.loads(line[6:])
                content.extend(choice.get('delta', {}).get('content') or '' for choice in event.get('choices', []))
                if event.get('timings') or event.get('usage'):
                    measurements.append({'seconds':time.monotonic()-started, 'timings':event.get('timings'),
                                         'usage':event.get('usage'), 'terminal':not event.get('choices') or any(choice.get('finish_reason') is not None for choice in event.get('choices', []))})
        live = [sample for sample in measurements if not sample['terminal']]
        assert len(live) >= 2, measurements
        assert all(sample['timings']['predicted_n'] >= 0 for sample in live)
        assert all(sample['usage']['context_window'] == 4096 for sample in measurements)
        assert measurements[-1]['terminal']
        assert ''.join(content).strip()
        report = {'model':model_id, 'measurements':measurements, 'content_characters':len(''.join(content))}
        (ROOT / 'logs/chat-metrics-native.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'model':model_id, 'live_samples':len(live), 'final_usage':measurements[-1], 'content_characters':report['content_characters']}))
    finally:
        if loaded:
            response = client.post(BASE + '/llamacpp/models/unload', json={'model_id':model_id})
            response.raise_for_status()
