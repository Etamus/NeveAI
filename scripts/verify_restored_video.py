"""Read-only preservation/readiness checks around the restored video cleanup."""
import argparse
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8080'
def get(path):
    with urllib.request.urlopen(BASE+path,timeout=30) as response:
        return json.load(response)

parser=argparse.ArgumentParser()
parser.add_argument('--capture',action='store_true')
args=parser.parse_args()
baseline_path=ROOT/'logs/video-restore-library-baseline.json'
rows=get('/api/v1/files/generated?limit=1000')
if args.capture:
    baseline_path.write_text(json.dumps(rows,indent=2),encoding='utf8')
    print('Captured generated-file IDs:',len(rows))
else:
    before=json.loads(baseline_path.read_text(encoding='utf8'))
    assert {item['id'] for item in before}<={item['id'] for item in rows}
    for item in before:
        request=urllib.request.Request(BASE+f"/api/v1/files/{item['id']}/content",headers={'Range':'bytes=0-0'})
        with urllib.request.urlopen(request,timeout=30) as response:
            assert response.status in (200,206)
            assert response.read(1),item['id']
    status=get('/api/v1/video-generation/status')
    assert not status['running'] and all(model['ready'] for model in status['models'].values())
    assert not get('/api/tasks')['tasks']
    encoders=ROOT/'backend/data/cache/video_generation/models/text_encoders'
    assert not (encoders/'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors').exists()
    assert not (encoders/'qwen3vl_8b_int8_convrot.safetensors').exists()
    shared=ROOT/'backend/data/cache/image_fast_generation/models/text_encoders/qwen3vl_8b_int8_convrot.safetensors'
    assert shared.stat().st_size==9350798360
    report=dict(status=status,original_generated_files_preserved=len(before),files_retrievable=True,
                removed_encoders_absent=True,shared_image_encoder_preserved=True)
    (ROOT/'logs/video-restore-final-smoke.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))
