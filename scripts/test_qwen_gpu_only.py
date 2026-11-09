"""Isolated llama-server probes. Does not change the application or NVIDIA settings."""
import json
from pathlib import Path
import re
import subprocess
import time

import httpx
import psutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'logs/qwen-memory-study'
BASE='http://127.0.0.1:8285'


def gpu():
    return subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,temperature.gpu','--format=csv,noheader,nounits'],text=True,creationflags=0x08000000).strip()


def wddm(pid):
    command=f"Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object {{$_.Name -like 'pid_{pid}_*'}} | Select-Object Name,DedicatedUsage,SharedUsage,TotalCommitted | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,timeout=30,creationflags=0x08000000)
    return json.loads(result.stdout) if result.stdout.strip() else None


with httpx.Client(timeout=120) as client:
    assert not any(m['is_loaded'] for m in client.get('http://127.0.0.1:8080/llamacpp/models').json()['models'])
    results=[]
    for label,ctx,cache,extra in [('full_4k',4096,'f16',[]),('full_32k',32768,'f16',[]),('full_32k_q8',32768,'q8_0',[]),('full_4k_nohost',4096,'f16',['--no-host'])]:
        args=[str(ROOT/'llamacpp-server/bin/llama-server.exe'),'--model',str(ROOT/'models/Qwen3.8-27B-UD-IQ4_XS.gguf'),'--host','127.0.0.1','--port','8285','--n-gpu-layers','all','--ctx-size',str(ctx),'--parallel','1','--flash-attn','on','--cache-type-k',cache,'--cache-type-v',cache,'--fit','off','--verbosity','5','--no-webui',*extra]
        result={'label':label,'context':ctx,'cache':cache,'command':args,'gpu_before':gpu()}
        log=OUT/f'{label}.log'
        with log.open('wb') as output:
            process=subprocess.Popen(args,cwd=ROOT/'llamacpp-server/bin',stdout=output,stderr=subprocess.STDOUT,creationflags=0x08000000)
            try:
                start=time.monotonic()
                while True:
                    if process.poll() is not None:raise RuntimeError(f'Server exited: {process.returncode}')
                    try:
                        if client.get(BASE+'/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    if time.monotonic()-start>120:raise TimeoutError('Startup deadline')
                    time.sleep(.25)
                result['load_seconds']=time.monotonic()-start
                p=psutil.Process(process.pid)
                result['gpu_loaded']=gpu();result['ram_loaded']=p.memory_full_info()._asdict()
                result['wddm_loaded']=wddm(process.pid)
                response=client.post(BASE+'/v1/chat/completions',json={'model':'test','messages':[{'role':'user','content':'List integers 1 to 100, one per line.'}],'max_tokens':128,'temperature':0,'stream':False})
                response.raise_for_status();result['timings']=response.json().get('timings');result['usage']=response.json().get('usage')
                result['gpu_after']=gpu();result['wddm_after']=wddm(process.pid);result['ram_after']=p.memory_full_info()._asdict()
            except Exception as error:
                result['error']=str(error)
            finally:
                if process.poll() is None:process.terminate()
                try:process.wait(10)
                except subprocess.TimeoutExpired:process.kill();process.wait(10)
        content=log.read_text(encoding='utf-8',errors='replace')
        result['allocations']=[line for line in content.splitlines() if re.search(r'offloaded|buffer size|using device|CUDA.*memory|CPU_Mapped|CPU_Host|model buffer|load_tensors.*mmap',line,re.I)]
        results.append(result);(OUT/'gpu-only.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
