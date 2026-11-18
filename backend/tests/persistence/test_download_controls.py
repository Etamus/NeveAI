import ast
import asyncio
import logging
import sys
import threading
from pathlib import Path
from typing import Optional



def test_cancel_while_worker_handle_is_being_acquired(tmp_path, monkeypatch):
    ns = runtime(tmp_path)
    ns['_HF_XET_DOWNLOAD_WORKER'] = "import time;time.sleep(30)"
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        native_spawn = asyncio.create_subprocess_exec
        actual = []
        async def delayed(*args, **kwargs):
            actual.append(await native_spawn(*args, **kwargs))
            started.set()
            await release.wait()
            return actual[0]
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', delayed)
        task = asyncio.create_task(ns['_xet_download_file']('t','repo/name','model.gguf',
                                                             tmp_path/'model.gguf',1,1,100))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled() and actual[0].returncode is not None
    asyncio.run(asyncio.wait_for(run(), 5))

from fastapi import APIRouter, HTTPException


def runtime(tmp_path):
    source = Path(__file__).resolve().parents[2] / 'neveai/routers/llamacpp.py'
    names = {'_launch_download', '_stop_download', '_get_task', '_get_model_download_lock',
             '_cleanup_download_artifacts', '_terminate_xet_process', '_xet_download_file',
             '_raise_if_download_cancelled', '_is_download_cancel_requested', '_retire_paused_downloads',
             '_DownloadCancelled'}
    tree = ast.parse(source.read_text(encoding='utf8'))
    tree.body = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names]
    tasks = {}
    ns = dict(asyncio=asyncio, Optional=Optional, Path=Path, sys=sys, log=logging.getLogger(__name__),
              HTTPException=HTTPException, _DOWNLOAD_RUNNERS={}, _DOWNLOAD_TASKS=tasks,
              _DOWNLOAD_TASKS_LOCK=threading.Lock(), _DOWNLOAD_MODEL_LOCKS={},
              _DOWNLOAD_MODEL_LOCKS_LOCK=threading.Lock(), _DOWNLOAD_ACTIVE_STATUSES={'queued','downloading','cancelling','pausing'},
              NEVE_DOWNLOAD_XET_MIN_SIZE=0, NEVE_DOWNLOAD_HEADERS={'User-Agent':'test'},
              NEVE_DOWNLOAD_PROGRESS_INTERVAL=.05, NEVE_DOWNLOAD_PROGRESS_BYTES=1)
    import time
    ns['time'] = time
    ns['_set_task'] = lambda task_id, **fields: tasks.setdefault(task_id, {'task_id':task_id}).update(fields)
    ns['_cleanup_new_xet_incomplete_files'] = lambda *args: None
    exec(compile(tree, str(source), 'exec'), ns)
    return ns


def test_repeated_immediate_cancel_only_affects_target(tmp_path):
    ns = runtime(tmp_path)
    async def run():
        ns['_set_task']('other', status='paused')
        for index in range(25):
            key = str(index)
            ns['_set_task'](key, status='queued')
            ns['_launch_download'](key, asyncio.sleep(30))
            state = await ns['_stop_download'](key, False)
            assert state['task']['status'] == 'cancelled'
            assert (await ns['_stop_download'](key, False))['task']['status'] == 'cancelled'
        assert ns['_get_task']('other')['status'] == 'paused'
        assert not ns['_DOWNLOAD_RUNNERS']
    asyncio.run(run())


def test_orphan_cancel_is_final_even_when_file_locked(tmp_path, monkeypatch):
    ns = runtime(tmp_path)
    part = tmp_path / 'file.part'; part.write_bytes(b'keep until handle closes')
    ns['_set_task']('orphan', status='cancelling', current_tmp_path=str(part))
    monkeypatch.setattr(Path, 'unlink', lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError('locked')))
    assert asyncio.run(ns['_stop_download']('orphan', False))['task']['status'] == 'cancelled'
    assert part.exists()


def test_pause_preserves_partial_and_cancel_removes_only_that_partial(tmp_path):
    ns = runtime(tmp_path)
    part = tmp_path / 'model.part'; part.write_bytes(b'partial')
    keep = tmp_path / 'other.gguf'; keep.write_bytes(b'other')
    async def run():
        ns['_set_task']('task', status='queued', current_tmp_path=str(part), model_id='model')
        ns['_launch_download']('task', asyncio.sleep(30))
        assert (await ns['_stop_download']('task', True))['task']['status'] == 'paused'
        assert part.read_bytes() == b'partial'
        assert (await ns['_stop_download']('task', False))['task']['status'] == 'cancelled'
        assert not part.exists() and keep.read_bytes() == b'other'
    asyncio.run(run())


def test_resumed_task_cannot_cancel_new_download(tmp_path):
    ns = runtime(tmp_path)
    part = tmp_path / 'model.part'; part.write_bytes(b'resumed data')
    ns['_set_task']('old', status='paused', model_id='same', current_tmp_path=str(part))
    ns['_retire_paused_downloads']('same')
    assert asyncio.run(ns['_stop_download']('old', False))['task']['status'] == 'resumed'
    assert part.read_bytes() == b'resumed data'


def test_cancelling_xet_awaits_child_exit_before_cleanup(tmp_path):
    ns = runtime(tmp_path)
    # The real subprocess holds the destination open, reproducing WinError 32.
    ns['_HF_XET_DOWNLOAD_WORKER'] = "import sys,time;from pathlib import Path;p=Path(sys.argv[3])/sys.argv[2];p.parent.mkdir(parents=True,exist_ok=True);f=p.open('wb');f.write(b'partial');f.flush();print('NEVE_XET_PROGRESS:7',flush=True);time.sleep(30)"
    destination = tmp_path / 'sub/Model.gguf'
    async def run():
        ns['_set_task']('task', status='queued')
        task = asyncio.create_task(ns['_xet_download_file']('task','Team/Repo','sub/Model.gguf',destination,1,1,100))
        for _ in range(100):
            if destination.exists(): break
            await asyncio.sleep(.02)
        assert destination.exists()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        destination.unlink()
        assert not destination.exists()
    asyncio.run(asyncio.wait_for(run(), 5))
