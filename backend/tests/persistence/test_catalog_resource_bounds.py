import asyncio
import json
import sys
import wave
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture(scope='module', autouse=True)
def bootstrap_routes():
    # Production migrations create config before importing the routers; this suite disables migrations.
    from neveai.internal.db import Base, engine
    with engine.begin() as db:
        db.exec_driver_sql('CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, data JSON, version INTEGER, created_at DATETIME, updated_at DATETIME)')
    from neveai.routers import audio, llamacpp
    Base.metadata.create_all(engine)


def test_transcription_blocks_preserve_every_sample(tmp_path):
    from neveai.routers.audio import _transcription_blocks

    path = tmp_path / 'recording.wav'
    samples = np.random.default_rng(1).integers(-32768, 32767, 173491, dtype=np.int16)
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', ''))
        output.writeframes(samples.tobytes())
    blocks = [x.copy() for x in _transcription_blocks(str(path), block_seconds=3)]
    assert len(blocks) > 3 and max(map(len, blocks)) <= 3 * 16000
    np.testing.assert_array_equal(np.concatenate(blocks), samples.astype(np.float32) / 32768)


def test_progress_ticks_skip_snapshots_and_retain_resumable_tasks(monkeypatch, tmp_path):
    from neveai.routers import llamacpp as rt

    calls = []
    class Tasks(dict):
        def items(self):
            calls.append(1)
            return super().items()

    tasks = Tasks({str(i): {'status': 'completed', 'finished_at': i} for i in range(100)})
    tasks.update(paused={'status': 'paused'}, retry={'status': 'error', 'resume_available': True})
    path = tmp_path / 'downloads.json'
    for key, value in dict(_DOWNLOAD_TASKS=tasks, NEVE_DOWNLOAD_STATE_DIR=tmp_path,
                           NEVE_DOWNLOAD_STATE_PATH=path, NEVE_DOWNLOAD_STATE_TMP_PATH=tmp_path / 'download.tmp',
                           NEVE_DOWNLOAD_PERSIST_INTERVAL=600).items():
        monkeypatch.setattr(rt, key, value)
    rt._set_task('active', status='downloading')
    assert len(tasks) == rt._DOWNLOAD_HISTORY_LIMIT + 3
    assert '0' not in tasks and '99' in tasks
    calls.clear()
    for i in range(100):
        rt._set_task('active', status='downloading', downloaded=i)
    assert not calls
    rt._set_task('active', status='paused')
    stored = json.loads(path.read_text())['tasks']
    assert stored['active']['downloaded'] == 99 and stored['active']['status'] == 'paused'
    assert 'paused' in stored and stored['retry']['resume_available']


def test_quantization_removal_preserves_other_files(monkeypatch, tmp_path):
    from neveai.routers import llamacpp as rt
    from neveai.utils import model_availability

    monkeypatch.setattr(rt, 'MODELS_DIR', tmp_path)
    monkeypatch.setattr(rt, '_find_active_download', lambda: None)
    monkeypatch.setitem(sys.modules, 'neveai.utils.middleware', SimpleNamespace(_MEDIA_GENERATION_LOCK=asyncio.Lock()))
    monkeypatch.setattr(model_availability, 'get_model_availability', lambda: {'busy': False})
    names = ['Demo-Q4-00001-of-00002.gguf', 'Demo-Q4-00002-of-00002.gguf', 'Demo-Q8.gguf',
             'backup-Demo-Q4-00001-of-00002.gguf', 'Demo-mmproj.gguf']
    for name in names:
        (tmp_path / name).touch()
    req = rt.DeleteLocalModelRequest(filename=names[0], preserve_encoders=True)
    result = asyncio.run(rt.delete_local_model(req, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))))
    assert result['removed_models'] == names[:2] and not result['removed_mmproj']
    assert all((tmp_path / name).is_file() for name in names[2:])
    assert '/catalog/delete' not in {route.path for route in rt.router.routes}
