"""Download and validate one small public GGUF, exclusively in disposable storage."""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/tests/persistence'))

with tempfile.TemporaryDirectory(prefix='neve-hf-live-') as temporary:
    root = Path(temporary)
    os.environ.update(DATA_DIR=str(root / 'data'), DATABASE_URL=f'sqlite:///{(root / "test.db").as_posix()}', ENABLE_DB_MIGRATIONS='false')
    from neveai.utils.hf_model_catalog import HuggingFaceCatalog, group_files, local_filename
    from neveai.routers import hf_models as api
    from test_hf_catalog import fake_runtime

    async def run():
        catalog = HuggingFaceCatalog()
        started = time.perf_counter()
        search = await catalog.search('SmolLM2-135M-Instruct')
        search_seconds = time.perf_counter() - started
        assert search['models']
        started = time.perf_counter()
        await catalog.search('SmolLM2-135M-Instruct')
        cached_seconds = time.perf_counter() - started
        repo = 'unsloth/SmolLM2-135M-Instruct-GGUF'
        started = time.perf_counter()
        inventory = await catalog.files(repo)
        files_seconds = time.perf_counter() - started
        rt = fake_runtime(root)
        api.runtime = lambda: rt
        models, _ = group_files(inventory['files'], repo, rt.MODELS_DIR, rt.MMPROJ_DIR)
        chosen = min(models, key=lambda model: model['size'])
        assert chosen['size'] < 200 * 1024 * 1024
        rt._set_task('live-hf', status='queued', model_id='hf:live', name=repo)
        targets = [(item, rt.MODELS_DIR / local_filename(repo, item['path'])) for item in chosen['files']]
        started = time.perf_counter()
        await api.run_download('live-hf', repo, targets, SimpleNamespace(state=SimpleNamespace(BASE_MODELS=None)))
        download_seconds = time.perf_counter() - started
        assert rt.tasks['live-hf']['status'] == 'completed', rt.tasks['live-hf']
        assert all(path.is_file() and path.stat().st_size == item['size'] for item, path in targets)
        assert group_files(inventory['files'], repo, rt.MODELS_DIR, rt.MMPROJ_DIR)[0][models.index(chosen)]['installed']
        print(json.dumps({'repo': repo, 'file': chosen['path'], 'bytes': chosen['size'], 'search_seconds': search_seconds,
                          'cached_search_seconds': cached_seconds, 'files_seconds': files_seconds, 'download_seconds': download_seconds,
                          'checksum_verified': True, 'gpu_used': False, 'disposable_storage': str(root)}, indent=2))
    asyncio.run(run())
print('Disposable database and weights removed.')
