"""Real chat/file generation regression; only disposable chat and file IDs are deleted."""
import io
import json
import threading
import time
from pathlib import Path
from zipfile import ZipFile

import pymupdf
import requests
import socketio
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'logs/document-tools-reliability'
OUT.mkdir(exist_ok=True, parents=True)
BASE = 'http://127.0.0.1:8080'
session = requests.Session()
socket = socketio.Client()
created_chats, created_files, task_ids = [], set(), []
events, finished, results = {}, {}, []


def api(method, path, **kwargs):
    response = session.request(method, BASE + path, timeout=240, **kwargs)
    response.raise_for_status()
    return response


@socket.on('events')
def receive(packet):
    chat = packet.get('chat_id')
    if chat not in events:
        return
    event = packet.get('data', {})
    events[chat].append(event)
    if event.get('type') == 'chat:message:files':
        created_files.update(item['id'] for item in event.get('data', {}).get('files', []))
    if (event.get('type') == 'chat:completion' and event.get('data', {}).get('done')) or event.get('type') == 'chat:message:error':
        finished[chat].set()


def run(label, messages, features=None, files=None):
    features = features if features is not None else {'file_generation': True}
    history = {f'm{i}': {**message, 'id': f'm{i}', 'parentId': f'm{i-1}' if i else None,
                        'childrenIds': [f'm{i+1}'] if i < len(messages)-1 else ['answer'], 'done': True}
               for i, message in enumerate(messages)}
    parent = f'm{len(messages)-1}'
    history['answer'] = {'id':'answer', 'parentId':parent, 'childrenIds':[], 'role':'assistant', 'content':'', 'done':False, 'model':model}
    chat = api('POST', '/api/v1/chats/new', json={'chat':{
        'title':'Temporary document validation: '+label, 'models':[model],
        'history':{'currentId':'answer', 'messages':history}, 'messages':list(history.values()), 'params':{}}}).json()['id']
    created_chats.append(chat)
    events[chat], finished[chat] = [], threading.Event()
    started = time.monotonic()
    response = api('POST', '/api/chat/completions', json={
        'model':model, 'messages':messages, 'features':features, 'files':files or [], 'stream':True,
        'chat_id':chat, 'id':'answer', 'parent_id':parent, 'parent_message':history[parent],
        'session_id':socket.get_sid(), 'background_tasks':{'title_generation':False,'tags_generation':False,'follow_up_generation':False},
        'params':{'reasoning_mode':'quick','no_think':True,'max_tokens':2048},
    }).json()
    if response.get('task_id'):
        task_ids.append(response['task_id'])
    assert finished[chat].wait(240), label + ': timeout'
    time.sleep(.25)
    answer = api('GET', '/api/v1/chats/'+chat).json()['chat']['history']['messages']['answer']
    created_files.update(item['id'] for item in answer.get('files', []))
    result = {'case':label,'seconds':round(time.monotonic()-started,2), 'answer':answer,
              'statuses':[event['data'] for event in events[chat] if event.get('type') == 'status']}
    results.append(result)
    (OUT / (label+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'case':label,'seconds':result['seconds'],'files':len(answer.get('files',[])), 'error':answer.get('error')}),flush=True)
    assert not answer.get('error'), answer.get('error')
    return answer, result


def generated(answer, extension):
    files = answer.get('files', [])
    assert len(files) == 1, answer
    data = api('GET', '/api/v1/files/'+files[0]['id']+'/content').content
    (OUT / ('output-'+str(len(results))+'.'+extension)).write_bytes(data)
    assert data, 'Empty file'
    return data, files[0]


try:
    user = api('GET', '/api/v1/auths/').json()
    session.headers['Authorization'] = 'Bearer '+user['token']
    assert not api('GET', '/api/tasks').json()['tasks'], 'User generation still active'
    models = api('GET', '/llamacpp/models').json()['models']
    loaded = [item for item in models if item['is_loaded']]
    if not loaded:
        snapshot = json.loads((ROOT / 'logs/tools-model-before.json').read_text())
        payload = {key:snapshot[key] for key in ('filename','n_gpu_layers','n_ctx','cache_type','speculative_decoding','token_prediction','context_shift','prioritize_gpu')}
        if snapshot.get('context_auto'):
            payload['n_ctx'] = 0
        payload['mmproj_filename'] = snapshot.get('mmproj_filename') or None
        api('POST', '/llamacpp/models/load', json=payload)
        loaded = [snapshot]
    model = loaded[0]['id']
    api('GET', '/api/models')
    socket.connect(BASE, socketio_path='ws/socket.io', auth={'token':user['token']}, transports=['websocket'])

    original_id = '67f51272-abe6-4d58-9b0a-e54df6ee19ac'
    original = api('GET','/api/v1/chats/'+original_id).json()
    exact_prompt = next(message['content'] for message in original['chat']['history']['messages'].values() if message['role']=='user')
    answer, _ = run('exact-original-pdf', [{'role':'user','content':exact_prompt}])
    data, first_pdf = generated(answer, 'pdf')
    with pymupdf.open(stream=data,filetype='pdf') as document:
        text = '\n'.join(page.get_text() for page in document)
        assert len(text.strip())>80 and 'batat' in text.casefold(), text
        document[0].get_pixmap().save(OUT/'exact-pdf.png')

    answer, result = run('thanks-after-pdf', [
        {'role':'user','content':exact_prompt}, {'role':'assistant','content':'Arquivo preparado.', 'files':[first_pdf]},
        {'role':'user','content':'Muito obrigado pela ajuda!'},
    ], files=[first_pdf])
    assert not answer.get('files') and not any(status.get('action')=='file_generation' for status in result['statuses'])

    answer, _ = run('three-paragraph-pdf', [{'role':'user','content':'Crie um PDF sobre batatas com exatamente tres paragrafos curtos, sem listas nem titulos.'}])
    before, source = generated(answer,'pdf')
    answer, _ = run('remove-last-paragraph', [
        {'role':'user','content':'Crie um PDF sobre batatas com tres paragrafos.'},
        {'role':'assistant','content':'Arquivo preparado.', 'files':[source]},
        {'role':'user','content':'Remova o ultimo paragrafo'},
    ], files=[source])
    after, _ = generated(answer,'pdf')
    with pymupdf.open(stream=before,filetype='pdf') as old, pymupdf.open(stream=after,filetype='pdf') as new:
        old_text='\n'.join(page.get_text() for page in old)
        new_text='\n'.join(page.get_text() for page in new)
        assert 0<len(new_text.strip())<len(old_text.strip())
        assert len(old)==len(new)
    assert api('GET','/api/v1/files/'+source['id']+'/content').content==before

    for extension, prompt in [
        ('docx','Crie um DOCX curto sobre fotossintese com um titulo e dois paragrafos.'),
        ('rtf','Crie um RTF com dois paragrafos curtos explicando como cuidar de plantas.'),
        ('xlsx','Crie um XLSX com as colunas Produto e Quantidade, com Arroz 2 e Feijao 3.'),
        ('pptx','Crie um PPTX com exatamente dois slides curtos sobre o ciclo da agua.'),
        ('json','Crie um arquivo JSON com o objeto {"produto":"batata","quantidade":3} sem outros campos.'),
    ]:
        answer, _ = run('create-'+extension,[{'role':'user','content':prompt}])
        data, _ = generated(answer,extension)
        if extension=='docx':
            assert len(' '.join(p.text for p in Document(io.BytesIO(data)).paragraphs))>40
        elif extension=='rtf':
            assert data.startswith(b'{\\rtf')
            from striprtf.striprtf import rtf_to_text
            text=rtf_to_text(data.decode('ascii'))
            assert len(text.strip())>80 and 'plant' in text.casefold(), text
        elif extension=='xlsx':
            book=load_workbook(io.BytesIO(data),read_only=True); rows=list(book.active.values);book.close()
            assert any('Arroz' in str(row) for row in rows) and any(3 in row for row in rows)
        elif extension=='pptx':
            assert len(Presentation(io.BytesIO(data)).slides)==2
        else:
            assert json.loads(data.decode('utf-8-sig'))=={'produto':'batata','quantidade':3}

    answer, result = run('web-and-pdf',[{'role':'user','content':'Pesquise na web e crie um PDF curto: em qual versao do Python foram introduzidas as dataclasses? Inclua as fontes.'}], {'web_search':True,'file_generation':True})
    data, _ = generated(answer,'pdf')
    assert any(status.get('action')=='web_search' for status in result['statuses'])
    with pymupdf.open(stream=data,filetype='pdf') as document:
        assert '3.7' in '\n'.join(page.get_text() for page in document)

    answer, result = run('learn-tools-conflict',[{'role':'user','content':'Me ensine o conceito de uma fracao com um exemplo simples.'}], {'guided_learning':True,'file_generation':True})
    assert not answer.get('files') and not any(status.get('action')=='file_generation' for status in result['statuses'])
    assert api('GET','/api/v1/chats/'+original_id).json()==original, 'Original user chat changed'
finally:
    for task in task_ids:
        try:
            api('POST','/api/tasks/stop/'+task)
        except requests.HTTPError:
            pass
    for chat in created_chats:
        api('DELETE','/api/v1/chats/'+chat)
    for file_id in created_files:
        api('DELETE','/api/v1/files/'+file_id)
    if socket.connected:
        socket.disconnect()
    (OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
