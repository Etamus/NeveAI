"""Opt-in real chat middleware test; temporary chat, no saved conversations."""
import json
import re
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8080'
with httpx.Client(timeout=240) as client:
    auth = client.get(BASE + '/api/v1/auths/')
    auth.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + auth.json()['token']
    models = client.get(BASE + '/llamacpp/models').json()['models']
    loaded = [model for model in models if model['is_loaded']]
    if not loaded:
        snapshot = json.loads((ROOT / 'logs/learn-model-before.json').read_text())
        payload = {key: snapshot[key] for key in ('filename','n_ctx','n_gpu_layers','mmproj_filename','cache_type','speculative_decoding','token_prediction','context_shift','prioritize_gpu')}
        if snapshot.get('context_auto'):
            payload['n_ctx'] = 0
        response = client.post(BASE + '/llamacpp/models/load', json=payload)
        response.raise_for_status()
        loaded = [snapshot]
    model_id = loaded[0]['id']
    client.get(BASE + '/api/models').raise_for_status()
    messages = [{'role':'user','content':'Quero aprender frações. Sei somar inteiros, mas não sei somar 1/2 + 1/4. Me ensine passo a passo.'}]
    results = []
    for followup in (None, 'Acho que 1/2 + 1/4 é 2/6.', 'Agora quero a resposta completa com a explicação, sem outra pergunta.'):
        if followup:
            messages.append({'role':'user','content':followup})
        response = client.post(BASE + '/api/chat/completions', json={
            'model':model_id, 'stream':False, 'messages':messages,
            'features':{'guided_learning':True}, 'chat_id':'local:guided-learning-validation',
            'reasoning_mode':'quick', 'no_think':True,
            'params':{'max_tokens':1200,'temperature':0.2},
        })
        response.raise_for_status()
        body = response.json()
        content = body['choices'][0]['message']['content']
        assert content and len(content) > 30, body
        results.append({'request':messages[-1]['content'],'response':content})
        messages.append({'role':'assistant','content':content})
    assert re.search(r'3\s*/\s*4|\\frac\{3\}\{4\}|¾', results[-1]['response']), results[-1]
    normal = client.post(BASE + '/api/chat/completions', json={
        'model':model_id, 'stream':False, 'features':{},
        'chat_id':'local:artifact-normal-validation', 'reasoning_mode':'quick','no_think':True,
        'messages':[{'role':'user','content':'Retorne apenas um bloco de código html com um documento HTML completo contendo um parágrafo NORMAL_OK. Não inclua explicações.'}],
        'params':{'max_tokens':250,'temperature':0.1},
    })
    normal.raise_for_status()
    normal_content = normal.json()['choices'][0]['message']['content']
    assert 'NORMAL_OK' in normal_content and '<html' in normal_content.lower(), normal_content
    (ROOT / 'logs/guided-learning-live.json').write_text(json.dumps({'model':model_id,'turns':results,'normal_artifact':normal_content},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'model':model_id,'turns':len(results),'characters':[len(item['response']) for item in results]}))
