"""Public Hugging Face GGUF browser using Neve's existing download task protocol."""
import asyncio
import hashlib
import os
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from neveai.utils.auth import get_admin_user, get_verified_user
from neveai.utils.hf_model_catalog import hf_catalog, group_files, download_filename

router = APIRouter()


def check_inside(root, path):
    base = root.resolve()
    if not path.resolve().is_relative_to(base):
        raise ValueError('O caminho sai da pasta de modelos.')
    current = path
    while current != root and current != current.parent:
        if current.is_symlink():
            raise ValueError('Links simbolicos nao sao permitidos no download.')
        current = current.parent


def runtime():
    from neveai.routers import llamacpp
    return llamacpp


def failure(exc):
    if isinstance(exc, ValueError):
        return HTTPException(400, str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        message = 'O repositorio exige acesso autorizado no Hugging Face.' if status in (401, 403) else 'O Hugging Face limitou as consultas. Tente novamente em instantes.' if status == 429 else 'Repositorio nao encontrado no Hugging Face.' if status == 404 else 'O Hugging Face nao respondeu corretamente.'
        return HTTPException(status if status in (401, 403, 404, 429) else 502, message)
    return HTTPException(502, 'Nao foi possivel consultar o Hugging Face. Tente novamente.')


@router.get('/search')
async def search_models(query: str = Query('', max_length=200), cursor: str | None = Query(None, max_length=4000), user=Depends(get_verified_user)):
    try:
        return await hf_catalog.search(query, cursor)
    except (ValueError, httpx.HTTPError) as exc:
        raise failure(exc)


def curated_entry(rt, repo):
    return next((entry for entry in getattr(rt, 'NEVE_CATALOG', ()) if entry['repo'] == repo), None)


async def inventory(repo):
    data = await hf_catalog.files(repo)
    rt = runtime()
    entry = curated_entry(rt, repo)
    models, encoders = await asyncio.to_thread(group_files, data['files'], repo, rt.MODELS_DIR, rt.MMPROJ_DIR,
                                              rt._catalog_repo_short(entry) if entry else None)
    return models, encoders, data['truncated']


@router.get('/files')
async def model_files(repo: str = Query(..., max_length=200), user=Depends(get_verified_user)):
    try:
        models, encoders, truncated = await inventory(repo)
        def public(rows):
            return [{key: value for key, value in row.items() if key != 'files'} for row in rows]
        return {'models': public(models), 'encoders': public(encoders), 'truncated': truncated}
    except (ValueError, httpx.HTTPError) as exc:
        raise failure(exc)


class HFDownloadRequest(BaseModel):
    repo: str = Field(max_length=200)
    filename: str = Field(max_length=500)
    encoder: str | None = Field(default=None, max_length=500)


def validate_weights(path, size, checksum):
    if path.stat().st_size != size:
        raise ValueError('O tamanho do arquivo baixado nao corresponde ao catalogo.')
    digest = hashlib.sha256() if checksum else None
    with path.open('rb') as source:
        header = source.read(8)
        if header[:4] != b'GGUF' or int.from_bytes(header[4:], 'little') not in (2, 3):
            raise ValueError('O arquivo baixado nao possui cabecalho GGUF valido.')
        if digest:
            digest.update(header)
            for chunk in iter(lambda: source.read(4 * 1024 * 1024), b''):
                digest.update(chunk)
    if digest and digest.hexdigest() != checksum:
        path.unlink(missing_ok=True)
        raise ValueError('Checksum do arquivo baixado nao confere.')


async def transfer(rt, task_id, repo, item, stage, index, count):
    path, size = item['path'], rt._hf_file_size(item)
    checksum = rt._hf_file_sha256(item)
    check_inside(rt.MODELS_DIR, stage)
    stage.parent.mkdir(parents=True, exist_ok=True)
    partial = stage.with_suffix(stage.suffix + '.part')
    rt._raise_if_download_cancelled(task_id)
    if stage.exists():
        try:
            await asyncio.to_thread(validate_weights, stage, size, checksum)
            return
        except ValueError:
            stage.unlink(missing_ok=True)
    if not stage.exists():
        used_xet = False if partial.exists() else await rt._xet_download_file(task_id, repo, path, stage, index, count, size)
        if not used_xet:
            partial = stage.with_suffix(stage.suffix + '.part')
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > size:
                partial.unlink()
                offset = 0
            headers = {**rt.NEVE_DOWNLOAD_HEADERS}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            token = os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN')
            if token:
                headers['Authorization'] = f'Bearer {token}'
            url = f'https://huggingface.co/{repo}/resolve/main/{quote(path, safe="/")}'
            rt._set_task(task_id, status='downloading', current_file=path, file_index=index, file_total=count,
                         current_tmp_path=str(partial), current_dest_path=str(stage), total=size, downloaded=offset, progress=offset / size)
            if offset < size:
                async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(90, connect=15)) as client:
                    async with client.stream('GET', url, headers=headers) as response:
                        response.raise_for_status()
                        if response.status_code == 206:
                            if not response.headers.get('content-range', '').startswith(f'bytes {offset}-'):
                                raise ValueError('Resposta de retomada invalida.')
                        else:
                            offset = 0
                        updated = time.monotonic()
                        with partial.open('ab' if offset else 'wb') as target:
                            async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                                rt._raise_if_download_cancelled(task_id)
                                if offset + len(chunk) > size:
                                    raise ValueError('O arquivo remoto excedeu o tamanho informado.')
                                await asyncio.to_thread(target.write, chunk)
                                offset += len(chunk)
                                if time.monotonic() - updated > 0.25:
                                    rt._set_task(task_id, downloaded=offset, progress=offset / size)
                                    updated = time.monotonic()
                            await asyncio.to_thread(target.flush)
                            await asyncio.to_thread(os.fsync, target.fileno())
            partial.replace(stage)
    rt._raise_if_download_cancelled(task_id)
    try:
        await asyncio.to_thread(validate_weights, stage, size, checksum)
    except ValueError:
        stage.unlink(missing_ok=True)
        raise
    partial.unlink(missing_ok=True)
    rt._set_task(task_id, downloaded=size, total=size, progress=1.0, verified=True)


async def run_download(task_id, repo, selected, app, identity=None, catalog_model=None):
    rt = runtime()
    published = []
    stage_root = rt.MODELS_DIR / '.hf-downloads' / hashlib.sha256((repo + (identity or '|'.join(item['path'] for item, _ in selected))).encode()).hexdigest()[:24]
    stages = [(item, destination, stage_root / item['path']) for item, destination in selected]
    rt._set_task(task_id, target_paths=[str(stage) for _, _, stage in stages],
                 tmp_paths=[str(stage.with_suffix(stage.suffix + '.part')) for _, _, stage in stages])
    try:
        for index, (item, destination, stage) in enumerate(stages, 1):
            rt._raise_if_download_cancelled(task_id)
            transfer_task = asyncio.create_task(transfer(rt, task_id, repo, item, stage, index, len(stages)))
            try:
                while not transfer_task.done():
                    await asyncio.wait({transfer_task}, timeout=0.2)
                    rt._raise_if_download_cancelled(task_id)
                await transfer_task
            finally:
                if not transfer_task.done():
                    transfer_task.cancel()
                await asyncio.gather(transfer_task, return_exceptions=True)
        for item, destination, stage in reversed(stages):
            rt._raise_if_download_cancelled(task_id)
            destination.parent.mkdir(parents=True, exist_ok=True)
            root = rt.MMPROJ_DIR if destination.parent == rt.MMPROJ_DIR else rt.MODELS_DIR
            check_inside(root, destination)
            # Hard-link publication is atomic and refuses to overwrite any existing model.
            def publish():
                os.link(stage, destination)
                published.append((destination, destination.stat().st_ino))
                stage.unlink()
            publication = asyncio.create_task(asyncio.to_thread(publish))
            try:
                await asyncio.shield(publication)
            except asyncio.CancelledError:
                await publication
                raise
        rt._raise_if_download_cancelled(task_id)
        if catalog_model:
            entry, filename = catalog_model
            if rt._apply_catalog_model_defaults(entry, filename) == 'failed':
                raise ValueError('Nao foi possivel aplicar as predefinicoes do modelo Neve.')
        app.state.BASE_MODELS = None
        rt._set_task(task_id, status='completed', progress=1.0, message='Download concluido', current_tmp_path=None, current_dest_path=None)
    except (rt._DownloadCancelled, asyncio.CancelledError) as exc:
        state = rt._get_task(task_id) if hasattr(rt, '_get_task') else rt.tasks.get(task_id, {}) if hasattr(rt, 'tasks') else {}
        paused = state.get('pause_requested', False)
        interrupted = isinstance(exc, asyncio.CancelledError) and not state.get('cancel_requested')
        pending = []
        if paused or interrupted:
            for path, inode in published:
                if path.exists() and path.stat().st_ino == inode:
                    stage = next(stage for _, destination, stage in stages if destination == path)
                    if not stage.exists():
                        os.link(path, stage)
                    path.unlink()
            rt._set_task(task_id, status='paused' if paused else 'error', resume_available=True,
                         error=None if paused else 'Download interrompido. Selecione o mesmo arquivo para continuar.')
            if interrupted:
                raise
            return
        for _, _, stage in stages:
            for path in (stage, stage.with_suffix(stage.suffix + '.part')):
                try:
                    check_inside(rt.MODELS_DIR, path)
                    for attempt in range(6):
                        try:
                            await asyncio.to_thread(path.unlink, missing_ok=True)
                            break
                        except PermissionError:
                            if attempt == 5:
                                raise
                            await asyncio.sleep(.1 * (attempt + 1))
                except OSError:
                    pending.append(str(path))
                    rt.log.warning('Download cancelled; cleanup deferred for locked file: %s', path)
        for path, inode in published:
            try:
                if path.exists() and path.stat().st_ino == inode:
                    path.unlink()
            except OSError:
                pending.append(str(path))
        rt._set_task(task_id, status='cancelled', progress=0.0, cleanup_pending=pending,
                     current_tmp_path=None, current_dest_path=None)
    except Exception as exc:
        for path, inode in published:
            if path.exists() and path.stat().st_ino == inode:
                path.unlink()
        rt.log.exception('Hugging Face download failed: %s', repo)
        app.state.BASE_MODELS = None
        rt._set_task(task_id, status='error', error=str(exc), resume_available=True)


@router.post('/download')
async def start_download(body: HFDownloadRequest, request: Request, user=Depends(get_admin_user)):
    rt = runtime()
    try:
        models, encoders, _ = await inventory(body.repo)
        model = next((row for row in models if row['path'] == body.filename), None)
        encoder = next((row for row in encoders if row['path'] == body.encoder), None) if body.encoder else None
        if model is None or body.encoder and encoder is None:
            raise ValueError('Selecione uma quantizacao e encoder presentes no repositorio.')
        selected = []
        entry = curated_entry(rt, body.repo)
        catalog_short = rt._catalog_repo_short(entry) if entry else None
        for group, root in [(model, rt.MODELS_DIR), *(([(encoder, rt.MMPROJ_DIR)]) if encoder else [])]:
            for item in group['files']:
                destination = root / download_filename(body.repo, item['path'], root, catalog_short)
                check_inside(root, destination)
                size = rt._hf_file_size(item)
                if size <= 0:
                    raise ValueError('O Hugging Face nao informou o tamanho deste arquivo.')
                if destination.exists() or destination.is_symlink():
                    if destination.is_symlink() or not destination.is_file() or destination.stat().st_size != size:
                        raise ValueError('Ja existe um arquivo diferente com esse nome. Nenhum arquivo foi substituido.')
                    continue
                selected.append((item, destination))
    except (ValueError, httpx.HTTPError) as exc:
        raise failure(exc)
    async with rt._MODEL_FILES_LOCK:
        if rt._find_active_download():
            raise HTTPException(409, 'Aguarde o download atual terminar.')
        if selected and sum(rt._hf_file_size(item) for item, _ in selected) + 64 * 1024 * 1024 > shutil.disk_usage(rt.MODELS_DIR).free:
            raise HTTPException(507, 'Espaco em disco insuficiente para este download.')
        task_id = uuid.uuid4().hex
        model_id = 'hf:' + hashlib.sha256((body.repo + '/' + body.filename).encode()).hexdigest()[:24]
        if hasattr(rt, '_retire_paused_downloads'):
            rt._retire_paused_downloads(model_id)
        rt._set_task(task_id, status='queued' if selected else 'completed', model_id=model_id, name=body.repo,
                     repo_id=body.repo, source='huggingface', filename=body.filename, encoder=body.encoder,
                     progress=0.0 if selected else 1.0)
        if selected:
            launch = getattr(rt, '_launch_download', lambda task_id, coroutine: asyncio.create_task(coroutine))
            catalog_model = (entry, model['local_filename']) if entry and any(dest.name == model['local_filename'] for _, dest in selected) else None
            launch(task_id, run_download(task_id, body.repo, selected, request.app, body.filename + '|' + (body.encoder or ''), catalog_model))
        return {'task_id': task_id, 'model_id': model_id, 'name': body.repo, 'status': 'queued' if selected else 'completed'}
