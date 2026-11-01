"""Check plain user-note comprehension with local inference; never persist chats/notes."""
import ast
import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unicodedata

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def main():
    contents = ["Meu nome e Marina", "Moro em Recife", "Prefiro respostas curtas",
                "No meu projeto uso Rust", "Nao como carne", "Minha reuniao de equipe e na quinta"]
    notes = [SimpleNamespace(id=str(i), content=text, updated_at=i) for i, text in enumerate(contents)]
    scope = dict(asyncio=asyncio, json=json, log=logging.getLogger(__name__),
                 has_permission=lambda *args: True,
                 Memories=SimpleNamespace(get_memories_by_user_id=lambda user: notes))
    for file, names in [
        ("backend/neveai/utils/misc.py", {"add_or_update_system_message", "update_message_content"}),
        ("backend/neveai/utils/middleware.py", {"chat_memory_handler"}),
    ]:
        tree = ast.parse((ROOT / file).read_text(encoding="utf-8-sig"))
        module = ast.parse("from __future__ import annotations")
        module.body.extend(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names)
        exec(compile(ast.fix_missing_locations(module), file, "exec"), scope)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=SimpleNamespace(ENABLE_MEMORIES=True, USER_PERMISSIONS={}))))
    results = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8080", timeout=180) as client:
        if (await client.get('/api/tasks')).json()['tasks'] or (await client.get('/llamacpp/models/loaded')).json()['models']:
            raise RuntimeError('Refusing to disturb an active task/model')
        model = 'local/Qwen3.5 9B MTP UDQ4_K_XL'
        loaded = False
        try:
            response = await client.post('/llamacpp/models/load', json=dict(filename='Qwen3.5 9B MTP UDQ4_K_XL.gguf', n_gpu_layers=99, n_ctx=8192, cache_type='q8_0', context_shift='off', speculative_decoding='off', token_prediction='off'))
            response.raise_for_status()
            loaded = True
            for question, expected in [
                ('Segundo minhas memorias, qual e meu nome, onde moro, qual linguagem uso no projeto, o que nao como e quando e minha reuniao? Responda em uma frase curta, sem introducao.', ['marina', 'recife', 'rust', 'carne', 'quinta']),
                ('Qual e minha cidade atual e qual linguagem uso no meu projeto? Responda de forma curta.', ['salvador', 'rust']),
            ]:
                if results:
                    notes[1].content = 'Moro em Salvador'
                    notes[1].updated_at = 100
                body = {'messages': [{'role': 'user', 'content': question}]}
                body = await scope['chat_memory_handler'](request, body, {}, SimpleNamespace(id='memory-fixture'))
                response = await client.post('/api/chat/completions', json=dict(
                    model=model, stream=False, messages=body['messages'], features={},
                    params={'think': False, 'temperature': 0, 'max_tokens': 384}, no_think=True,
                    background_tasks={'title_generation': False, 'follow_up_generation': False, 'tags_generation': False},
                ))
                response.raise_for_status()
                answer = response.json()['choices'][0]['message']['content']
                normalized = ''.join(c for c in unicodedata.normalize('NFD', answer.lower()) if not unicodedata.combining(c))
                assert all(word in normalized for word in expected), answer
                if results:
                    assert 'recife' not in normalized, answer
                results.append(dict(question=question, answer=answer, passed=True))
                print(json.dumps(results[-1], ensure_ascii=True), flush=True)
        finally:
            if loaded:
                response = await client.post('/llamacpp/models/unload', json={'model_id': model})
                response.raise_for_status()
            (ROOT / 'logs/memory-context-live.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
