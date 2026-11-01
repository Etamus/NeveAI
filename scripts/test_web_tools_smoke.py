"""Read-only API smoke plus disposable document generation; no LLM/GPU calls."""
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
BASE = 'http://127.0.0.1:8080'
results = []
for label, payload in [
    ('short_pdf', {'queries': [], 'urls': ['https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'], 'question': 'Leia o PDF'}),
    ('web', {'queries': ['Python official documentation tutorial'], 'question': 'Pesquise a documentacao oficial do Python'}),
]:
    start = time.monotonic()
    response = requests.post(BASE + '/api/v1/retrieval/process/web/search', json=payload, timeout=65)
    response.raise_for_status()
    result = response.json()
    assert result['status'] and result['pages_read_count'] > 0, result
    results.append({'case': label, 'seconds': round(time.monotonic() - start, 2),
                    'pages': result['pages_read_count'], 'snippets': result['snippet_count']})

for path in ['/health', '/api/tasks', '/api/v1/chats/', '/api/v1/files/generated?limit=50', '/api/v1/memories/']:
    response = requests.get(BASE + path, timeout=30)
    response.raise_for_status()
    results.append({'path': path, 'status': response.status_code})

from neveai.utils.generated_files import build_generated_file
from neveai.utils.document_validation import validate_document_output

for fmt, content in {
    'docx': '# Report\n\nPreserved document content.',
    'xlsx': json.dumps({'sheets': [{'name': 'Sheet', 'rows': [['Item', 'Value'], ['One', 12.5]]}]}),
    'pptx': json.dumps({'slides': [{'title': 'Summary', 'content': ['First point', 'Second point']}]}),
    'pdf': '# Report\n\nPreserved document content.',
}.items():
    _, data, _ = build_generated_file('test.' + fmt, content, fmt, prefer_officecli=True)
    report = validate_document_output(data, fmt, content)
    assert report['validation'] == 'passed'
    results.append({'format': fmt, 'bytes': len(data), 'validation': report['validation']})

(ROOT / 'logs/web-tools-smoke.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results))
