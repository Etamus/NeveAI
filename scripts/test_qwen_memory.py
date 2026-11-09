"""Local opt-in VRAM diagnostic; no model preset or chat is saved."""
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess
import threading
import time

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'logs/qwen-memory-study'
OUT.mkdir(exist_ok=True)
BASE = 'http://127.0.0.1:8080'
TARGET = 'Qwen3.8-27B-UD-IQ4_XS.gguf'


def gpu():
    value = subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.total,temperature.gpu','--format=csv,noheader,nounits'],creationflags=0x08000000,text=True).strip()
    return [int(x.strip()) for x in value.split(',')]


def wddm(pid):
    command = f"Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object {{$_.Name -like 'pid_{pid}_*'}} | Select-Object Name,DedicatedUsage,SharedUsage,TotalCommitted | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,timeout=30,creationflags=0x08000000)
    return json.loads(result.stdout) if result.stdout.strip() else None


def runtime():
    for process in psutil.process_iter(['pid','name','exe','cmdline']):
        if (process.info['name'] or '').lower() == 'llama-server.exe' and ROOT in Path(process.info['exe']).parents:
            return process
    raise RuntimeError('Workspace llama-server not found')


with httpx.Client(timeout=180) as client, concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    previous = [m for m in client.get(BASE+'/llamacpp/models').json()['models'] if m['is_loaded']]
    if previous:
        raise RuntimeError('Diagnostic requires an idle runtime with no models loaded')
    report = {'baseline_gpu':gpu(),'cases':[]}
    for label, context, cache in [('automatic',0,'f16'),('all_gpu_4k',4096,'f16')]:
        result = {'label':label,'requested_context':context,'cache':cache,'gpu_before':gpu()}
        loaded = False
        try:
            start = time.monotonic()
            response = client.post(BASE+'/llamacpp/models/load',json={'filename':TARGET,'n_ctx':context,'n_gpu_layers':-1,'cache_type':cache})
            response.raise_for_status();loaded=True
            result['load_seconds']=time.monotonic()-start
            result['applied']=response.json()
            proc=runtime();result['command']=proc.cmdline()
            result['ram_after_load']=proc.memory_full_info()._asdict()
            result['gpu_after_load']=gpu();result['wddm_after_load']=wddm(proc.pid)
            during = pool.submit(wddm,proc.pid)
            measurements=[];text=[];start=time.monotonic()
            with client.stream('POST',BASE+'/llamacpp/chat/completions',json={'model':'local/'+TARGET[:-5],'messages':[{'role':'user','content':'List the integers 1 through 100, one per line. Start immediately.'}],'stream':True,'max_tokens':128,'temperature':0}) as stream:
                stream.raise_for_status()
                for line in stream.iter_lines():
                    if not line.startswith('data: ') or line[6:]=='[DONE]':continue
                    event=json.loads(line[6:])
                    text.extend(c.get('delta',{}).get('content') or '' for c in event.get('choices',[]))
                    if event.get('timings'):measurements.append(event['timings'])
            result.update(generation_seconds=time.monotonic()-start,measurements=measurements,content_characters=len(''.join(text)),wddm_during=during.result(),gpu_after_generation=gpu(),ram_after_generation=proc.memory_full_info()._asdict())
        except Exception as error:
            result['error']=str(error)
        finally:
            log=ROOT/'logs/llamacpp/local_Qwen3.8-27B-UD-IQ4_XS.log'
            if log.exists():
                content=log.read_text(encoding='utf-8',errors='replace')
                (OUT/f'{label}.log').write_text(content,encoding='utf-8')
                result['allocation_log']=[line for line in content.splitlines() if re.search(r'offload|buffer size|Vulkan|CUDA|n_ctx|fit_params',line,re.I)]
            if loaded:client.post(BASE+'/llamacpp/models/unload',json={'model_id':'local/'+TARGET[:-5]}).raise_for_status()
            result['gpu_after_unload']=gpu()
            report['cases'].append(result)
            (OUT/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(result),flush=True)
