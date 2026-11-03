"""Read-only post-activation checks and preservation of original library IDs."""
import json
import argparse
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--baseline',type=Path,default=ROOT/'logs/video-prompt-audit-20261102/saved-prompts.json')
parser.add_argument('--output',type=Path,default=ROOT/'logs/video15-final-smoke.json')
args=parser.parse_args()
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=20) as response:
        assert response.status==200
        return json.load(response)

health=get('/health')
tasks=get('/api/tasks')
status=get('/api/v1/video-generation/status')
loaded=get('/llamacpp/models/loaded')
files=get('/api/v1/files/generated?kind=video&limit=100')
baseline=json.loads(args.baseline.read_text(encoding='utf8'))
assert not tasks['tasks']
assert not status['running']
assert all(model['ready'] for model in status['models'].values())
assert not loaded['models']
missing={row['id'] for row in baseline}-{row['id'] for row in files}
assert not missing, missing
results=dict(health=health,tasks=tasks,status=status,loaded=loaded,
             original_library_ids_preserved=len(baseline),video_files=len(files))
args.output.write_text(json.dumps(results,indent=2),encoding='utf8')
print(json.dumps(results))
