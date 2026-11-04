import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request
import psutil

root = Path(__file__).resolve().parents[1]
base = 'http://127.0.0.1:8080'
for attempt in range(90):
    try:
        with urllib.request.urlopen(base + '/health', timeout=1) as response:
            assert json.load(response)['status']
        break
    except Exception:
        if attempt == 89:
            raise
        time.sleep(0.5)
owner = next(connection.pid for connection in psutil.net_connections(kind='tcp') if connection.status == psutil.CONN_LISTEN and connection.laddr.port == 8080)
environment = psutil.Process(owner).environ()
assert environment.get('NEVE_USE_PUBLISHED_FRONTEND') == '1', 'Normal launcher must select published frontend'
published = root / 'backend/neveai/frontend/index.html'
with urllib.request.urlopen(base, timeout=5) as response:
    html = response.read()
assert hashlib.sha256(html).digest() == hashlib.sha256(published.read_bytes()).digest(), 'Active frontend differs from published frontend'
entries = set(re.findall(rb'_app/immutable/entry/[^"\s]+\.js', html))
for entry in entries:
    with urllib.request.urlopen(base + '/' + entry.decode(), timeout=5) as response:
        assert response.status == 200
with urllib.request.urlopen(base + '/llamacpp/vram', timeout=10) as response:
    memory = json.load(response)
ram = memory['ram']
assert ram['available'] and ram['total'] > 0
assert ram['used'] + ram['free'] == ram['total']
result = {'health': True, 'published_frontend': True, 'entry_assets_checked': len(entries), 'ram_available': True, 'ram_total': ram['total'], 'gpu_available': memory['available']}
(root / 'logs/installer-activation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
