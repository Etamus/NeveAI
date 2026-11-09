"""Opt-in GPU smoke test of the new load profile; no chat or preset is saved."""
import json
from pathlib import Path
import time

import httpx
import psutil

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8080'
FILENAME='Qwen3.8-27B-UD-IQ4_XS.gguf'
MODEL='local/'+FILENAME[:-5]


def runtime():
    return next(p for p in psutil.process_iter(['pid','name','exe']) if (p.info['name'] or '').lower()=='llama-server.exe' and ROOT in Path(p.info['exe']).parents)


with httpx.Client(timeout=180) as client:
    assert client.get(BASE+'/llamacpp/status').json()['gpu_priority_supported']
    assert not any(m['is_loaded'] for m in client.get(BASE+'/llamacpp/models').json()['models'])
    results=[];loaded=False
    try:
        for label,context,cache,priority in [('gpu_auto',0,'f16',True),('gpu_manual',4096,'q8_0',True),('original_auto',0,'f16',False)]:
            payload={'filename':FILENAME,'n_ctx':context,'n_gpu_layers':-1,'mmproj_filename':'','cache_type':cache,'prioritize_gpu':priority}
            response=client.post(BASE+'/llamacpp/models/load',json=payload);response.raise_for_status();loaded=True
            applied=response.json();proc=runtime();command=proc.cmdline()
            assert applied['prioritize_gpu']==priority
            assert applied['context_auto']==(context==0)
            assert applied['cache_type']==cache
            if context:assert applied['n_ctx']==context
            if priority:
                assert command[command.index('--n-gpu-layers')+1]=='all'
                assert command[command.index('--fit')+1]=='off'
            else:
                assert command[command.index('--n-gpu-layers')+1]!='all'
            again=client.post(BASE+'/llamacpp/models/load',json=payload);again.raise_for_status()
            # The original fitter may store its applied layer count instead of -1;
            # priority keeps a stable full-GPU profile and must not reload on reuse.
            if priority:assert runtime().pid==proc.pid
            measurements=[];start=time.monotonic()
            with client.stream('POST',BASE+'/llamacpp/chat/completions',json={'model':MODEL,'messages':[{'role':'user','content':'List integers 1 to 100, one per line.'}],'max_tokens':128,'temperature':0,'stream':True}) as stream:
                stream.raise_for_status()
                for line in stream.iter_lines():
                    if not line.startswith('data: ') or line[6:]=='[DONE]':continue
                    event=json.loads(line[6:])
                    if event.get('timings'):measurements.append(event['timings'])
            assert measurements and measurements[-1]['predicted_n']>0
            results.append({'case':label,'applied':applied,'command':command,'seconds':time.monotonic()-start,'timings':measurements[-1]})
            print(json.dumps(results[-1]),flush=True)
        (ROOT/'logs/gpu-priority-live.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    finally:
        if loaded:client.post(BASE+'/llamacpp/models/unload',json={'model_id':MODEL}).raise_for_status()
