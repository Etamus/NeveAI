"""Freeze the current Video 1.5 graphs for exact retirement regression checks."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from test_video_quality_generation import quality_namespace

runtime = quality_namespace(Path('test-cache'))['NeveVideo15Runtime']
cases = []
for width, height in ((864, 480), (1184, 672), (480, 864)):
    for frames in (124, 196):
        for references in ((None, None), ('first.png', None), (None, 'last.png'), ('first.png', 'last.png')):
            for merged in (False, True):
                args = ('Original request with "literal words" and accents: caf\u00e9.', 12345, *references, width, height, frames, merged)
                cases.append({'args': args, 'graph': runtime._build_workflow(*args)})
output = ROOT / 'logs/video1-retirement-workflows-before.json'
output.write_text(json.dumps(cases, ensure_ascii=True, indent=2), encoding='utf8')
print(f'{len(cases)} Video 1.5 workflows saved')
