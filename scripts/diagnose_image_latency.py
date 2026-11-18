"""Read-only chat evidence and temporary inference timing; never persists a chat."""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import urlopen

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from neveai.routers.image_fast_generation import neve_image_2s_runtime
from neveai.routers.image_quality_generation import neve_image_21_runtime
from neveai.routers.video_generation import shared_h3_runtime

OUT = ROOT / 'logs/image-latency-20261114'
OUT.mkdir(parents=True, exist_ok=True)


async def measure(label, runtime, reference):
    record = dict(model=label, phases=[], progress=[], loop_stalls=[], min_ram_free_gib=100, peak_vram_mib=0)
    started = time.perf_counter()
    originals = {}
    for name in ('_install', '_models', '_ensure_models', '_start', '_start_comfy', '_plan_edit', '_stop'):
        if not hasattr(runtime, name):
            continue
        original = getattr(runtime, name)
        if not asyncio.iscoroutinefunction(original):
            continue
        originals[name] = original
        def wrap(original, name):
            async def tracked(*args, **kwargs):
                begin = time.perf_counter()
                phase = dict(name=name, start=round(begin-started,3))
                try:
                    return await original(*args, **kwargs)
                finally:
                    phase['seconds'] = round(time.perf_counter()-begin,3)
                    record['phases'].append(phase)
                    print('PHASE', label, phase, flush=True)
            return tracked
        setattr(runtime, name, wrap(original, name))
    async def heartbeat():
        previous = time.perf_counter()
        while True:
            await asyncio.sleep(.01)
            now = time.perf_counter()
            delay = now-previous-.01
            if delay > .05:
                record['loop_stalls'].append(dict(at=round(now-started,3),milliseconds=round(delay*1000,2)))
            previous = now
    async def hardware():
        while True:
            free = psutil.virtual_memory().available/1024**3
            record['min_ram_free_gib'] = min(record['min_ram_free_gib'], free)
            process = await asyncio.create_subprocess_exec('nvidia-smi','--query-gpu=memory.used,temperature.gpu','--format=csv,noheader,nounits',
                stdout=asyncio.subprocess.PIPE, **({'creationflags':0x08000000} if os.name=='nt' else {}))
            raw,_=await process.communicate()
            used,temp=map(int,raw.decode().strip().split(','))
            record['peak_vram_mib']=max(record['peak_vram_mib'],used)
            if free < .8 or temp > 80:
                raise RuntimeError('Hardware safety limit reached')
            await asyncio.sleep(1)
    async def progress(value):
        if not record['progress'] or record['progress'][-1]['value'] != value:
            record['progress'].append(dict(value=value,at=round(time.perf_counter()-started,3)))
            print('PROGRESS',label,record['progress'][-1],flush=True)
    async def dimensions(w,h):
        record['dimensions']=[w,h]
    tick=asyncio.create_task(heartbeat())
    hw=asyncio.create_task(hardware())
    print('BEGIN',label,flush=True)
    try:
        async with asyncio.timeout(900):
            output=await runtime.run('Fa\u00e7a ela sorrindo de boca aberta','auto',[reference],None,progress,dimensions)
        (OUT/(label+'.png')).write_bytes(base64.b64decode(output.split(',',1)[1]))
    except Exception as error:
        record['error']=repr(error)
        raise
    finally:
        record['seconds']=round(time.perf_counter()-started,3)
        for task in (tick,hw):
            task.cancel()
        await asyncio.gather(tick,hw,return_exceptions=True)
        (OUT/(label+'-result.json')).write_text(json.dumps(record,indent=2),encoding='utf8')
        (OUT/(label+'-worker.log')).write_text('\n'.join(runtime._log_tail),encoding='utf8')
        for name, original in originals.items():
            setattr(runtime,name,original)
        print('COMPLETE',label,record['seconds'], 'max_loop_ms',max((v['milliseconds'] for v in record['loop_stalls']),default=0),flush=True)


async def main():
    tasks=json.load(urlopen('http://127.0.0.1:8080/api/tasks'))
    loaded=json.load(urlopen('http://127.0.0.1:8080/llamacpp/models/loaded'))
    assert not tasks['tasks'] and not loaded['models'], 'Keep existing GPU work untouched'
    raw=(ROOT/'backend/data/uploads/0e335168-40a8-473e-a233-1dd5f1cfb0c6_image.png').read_bytes()
    reference='data:image/png;base64,'+base64.b64encode(raw).decode()
    await shared_h3_runtime._apply_safe_power_limit()
    try:
        for label,runtime in [('image2-cold',neve_image_2s_runtime),('image28-cold',neve_image_21_runtime),('image2-warm',neve_image_2s_runtime)]:
            await measure(label,runtime,reference)
    finally:
        await shared_h3_runtime._restore_power_limit()


asyncio.run(main())
