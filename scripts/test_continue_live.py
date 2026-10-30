"""Read-only inference comparison on the already-loaded llama-server; no chat persistence."""
import json
from pathlib import Path
import time
import urllib.request
import ast
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

base = 'http://127.0.0.1:8281'
results = []
messages = [
    {'role': 'user', 'content': 'Conte uma historia longa em portugues, com varios paragrafos.'},
    {'role': 'assistant', 'content': 'Era uma vez uma viajante chamada Lia. Ela encontrou uma porta misteriosa no fundo da biblioteca.'},
]
if os.environ.get('LIVE_SAVED_CONTEXT'):
    scope = dict(json=json)
    misc_tree = ast.parse(Path('backend/neveai/utils/misc.py').read_text(encoding='utf-8-sig'))
    converter = next(node for node in misc_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'convert_output_to_messages')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[converter], type_ignores=[])), 'real-converter', 'exec'), scope)
    with urllib.request.urlopen('http://localhost:8080/api/v1/chats/71798977-ce6a-401a-9033-a38d80a2f596') as response:
        history = json.load(response)['chat']['history']
    chain = []
    current = history['currentId']
    while current:
        item = history['messages'][current]
        chain.append(item)
        current = item.get('parentId')
    messages = []
    for item in reversed(chain):
        if item.get('output'):
            messages.extend(scope['convert_output_to_messages'](item['output'], raw=True))
        else:
            messages.append({'role': item['role'], 'content': item['content']})
tree = ast.parse(Path('backend/neveai/utils/middleware.py').read_text(encoding='utf-8'))
function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'process_chat_payload')
continuation_branch = next(node for node in function.body if isinstance(node, ast.If) and 'Continue your previous response' in ast.unparse(node))
for mode in ['prefill', 'followup']:
    data = {'messages': list(messages)}
    if mode == 'followup':
        exec(compile(ast.fix_missing_locations(ast.Module(body=[continuation_branch], type_ignores=[])), 'real-continue', 'exec'),
             dict(form_data=data, metadata={'continue_response': True}))
    request_messages = data['messages']
    body = dict(messages=request_messages, stream=True, max_tokens=192, temperature=0,
                chat_template_kwargs={'enable_thinking': False}, reasoning_format='none')
    start = time.monotonic()
    text = ''
    events = []
    request = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=90) as response:
        for line in response:
            if not line.startswith(b'data: '):
                continue
            value = line[6:].strip()
            if value == b'[DONE]':
                break
            event = json.loads(value)
            events.append(event)
            for choice in event.get('choices', []):
                text += choice.get('delta', {}).get('content') or ''
    results.append(dict(mode=mode, seconds=time.monotonic()-start, text=text, events=events))
Path(os.environ.get('LIVE_RESULT', 'logs/continue-live-comparison.json')).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
for result in results:
    print(json.dumps({k: v for k, v in result.items() if k != 'events'}, ensure_ascii=False))
