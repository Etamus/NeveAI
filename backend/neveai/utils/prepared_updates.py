"""Download updates without mutating the running installation."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from neveai.utils.llamacpp_updates import compatible_backend, installed_backend, _release_tags, _release_from_assets

HOSTS = {'api.github.com', 'github.com', 'codeload.github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
RELEASE_FILES = (
    'instalar.bat', 'launchers/instalar.ps1', 'launchers/instalar.vbs',
    'launchers/iniciar.ps1', 'launchers/iniciar.vbs', 'launchers/update-core.ps1',
    'launchers/apply-update.ps1', 'launchers/runtime-validation.ps1',
    'launchers/process-ownership.ps1', 'launchers/installer-release-cache.ps1',
    'backend/neveai/__init__.py', 'backend/neveai/main.py',
    'backend/neveai/routers/music_generation.py', 'backend/neveai/routers/video_generation.py',
    'backend/neveai/models/users.py', 'backend/neveai/models/models.py',
    'backend/neveai/models/auths.py', 'backend/neveai/routers/auths.py',
    'backend/neveai/utils/auth.py', 'backend/neveai/utils/prepared_updates.py',
    'desktop/runtime.json', 'desktop/setup_runtime.py', 'desktop/NeveWindow.cs',
    'desktop/app.manifest', 'desktop/verify-runtime.ps1', 'desktop/profile_migration.py',
    'package.json',
)


def validate_archive(path):
    with zipfile.ZipFile(path) as archive:
        if not archive.infolist():
            raise ValueError('O pacote de atualização está vazio.')
        if len(archive.infolist()) > 200000 or sum(item.file_size for item in archive.infolist()) > 16 * 1024**3:
            raise ValueError('O pacote expandido excede o tamanho permitido.')
        for item in archive.infolist():
            name = item.filename.replace('\\', '/')
            parts = PurePosixPath(name)
            if parts.is_absolute() or '..' in parts.parts or ':' in name or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('O pacote contém um caminho inseguro.')
        if archive.testzip() is not None:
            raise ValueError('O pacote de atualização está corrompido.')


def validate_package(path, kind):
    validate_archive(path)
    with zipfile.ZipFile(path) as archive:
        names = {item.filename.replace('\\', '/').rstrip('/') for item in archive.infolist() if not item.is_dir()}
        if kind == 'neve.zip':
            roots = {name.split('/')[0] for name in names}
            if len(roots) != 1:
                raise ValueError('Estrutura inesperada da release do NeveAI.')
            prefix = next(iter(roots)) + '/'
            missing = [name for name in RELEASE_FILES if prefix + name not in names]
            if missing:
                raise ValueError('Release incompleta ou incompativel. Nenhum arquivo local foi alterado: ' + ', '.join(missing))
        elif kind == 'llama.zip' and not any(name.rsplit('/', 1)[-1].lower() == 'llama-server.exe' for name in names):
            raise ValueError('O pacote do llama.cpp nao contem llama-server.exe.')
        elif kind == 'runtime.zip' and not any(name.lower().endswith('.dll') for name in names):
            raise ValueError('O pacote CUDA nao contem as bibliotecas esperadas.')


class PreparedUpdates:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.directory = self.root / 'backend/data/updates'
        self.task = None
        self.lock = asyncio.Lock()

    def _write(self, job):
        folder = self.directory / job['id']
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'manifest.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
        for attempt in range(10):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(.025)

    def state(self, user_id):
        if not self.directory.exists():
            return {'status': 'idle'}
        paths = sorted(self.directory.glob('*/manifest.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths:
            try:
                job = json.loads(path.read_text(encoding='utf-8'))
                if job.get('owner') != str(user_id):
                    continue
                if job.get('status') == 'downloading' and (self.task is None or self.task.done()):
                    job.update(status='failed', error='O download foi interrompido. Tente novamente.')
                    self._write(job)
                return {k: job.get(k) for k in ('id', 'status', 'progress', 'phase', 'error', 'targets', 'versions')}
            except (OSError, ValueError):
                continue
        return {'status': 'idle'}

    async def start(self, targets, user_id):
        async with self.lock:
            if self.task and not self.task.done():
                raise ValueError('Já existe um download de atualização em andamento.')
            if not targets or set(targets) - {'neve', 'llama'}:
                raise ValueError('Selecione NeveAI ou llama.cpp.')
            for path in self.directory.glob('*/manifest.json'):
                try:
                    existing = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                if existing.get('status') in {'ready', 'restarting', 'applying'}:
                    raise ValueError('Uma atualização já está preparada para reiniciar.')
            job = {'id': uuid.uuid4().hex, 'owner': str(user_id), 'root': str(self.root),
                   'targets': list(dict.fromkeys(targets)), 'status': 'downloading', 'progress': 0,
                   'phase': 'Preparando download', 'versions': {}, 'packages': [], 'created': time.time()}
            self._write(job)
            self.task = asyncio.create_task(self._prepare(job))
            return self.state(user_id)

    async def _get(self, client, url, **kwargs):
        # Release URLs are selected on the server; validate redirect hosts as well.
        for _ in range(8):
            if httpx.URL(url).scheme != 'https' or httpx.URL(url).host not in HOSTS:
                raise ValueError('Endereço de atualização não permitido.')
            response = await client.get(url, follow_redirects=False, **kwargs)
            if response.is_redirect:
                url = str(response.url.join(response.headers['location']))
                continue
            response.raise_for_status()
            return response
        raise ValueError('Redirecionamentos excessivos no download.')

    async def _download(self, client, url, destination, progress):
        for attempt in range(3):
            try:
                return await self._download_once(client, url, destination, progress)
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code not in {408, 429, 500, 502, 503, 504}:
                    raise
                if attempt == 2:
                    raise
                await asyncio.sleep(attempt + 1)

    async def _download_once(self, client, url, destination, progress):
        for _ in range(8):
            if httpx.URL(url).scheme != 'https' or httpx.URL(url).host not in HOSTS:
                raise ValueError('Endereço de download não permitido.')
            async with client.stream('GET', url, follow_redirects=False) as response:
                if response.is_redirect:
                    url = str(response.url.join(response.headers['location']))
                    continue
                response.raise_for_status()
                expected = int(response.headers.get('content-length', 0))
                digest, received = hashlib.sha256(), 0
                last = 0
                with destination.open('wb') as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        received += len(chunk)
                        if received > 8 * 1024**3:
                            raise ValueError('O pacote excede o tamanho permitido.')
                        await asyncio.to_thread(output.write, chunk)
                        digest.update(chunk)
                        if time.monotonic() - last > .15:
                            progress(received / expected if expected else 0)
                            last = time.monotonic()
                if expected and received != expected:
                    raise ValueError('O download terminou incompleto.')
                return digest.hexdigest(), received
        raise ValueError('Redirecionamentos excessivos no download.')

    async def _neve_release(self, client):
        try:
            return (await self._get(client, 'https://api.github.com/repos/Etamus/NeveAI/releases/latest')).json()
        except (httpx.HTTPError, ValueError, KeyError):
            response = await self._get(client, 'https://github.com/Etamus/NeveAI/releases/latest', headers={'Accept': 'text/html'})
            tag = response.url.path.rsplit('/', 1)[-1]
            if not re.fullmatch(r'v?\d+(?:\.\d+)+(?:[-+][\w.-]+)?', tag):
                raise ValueError('Nao foi possivel confirmar a release publicada.')
            return {'tag_name': tag, 'zipball_url': f'https://codeload.github.com/Etamus/NeveAI/zip/refs/tags/{tag}'}

    async def _llama_releases(self, client):
        try:
            releases = (await self._get(client, 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30')).json()
            if isinstance(releases, list):
                return releases
        except (httpx.HTTPError, ValueError):
            pass
        async def html(path):
            return (await self._get(client, f'https://github.com/ggml-org/llama.cpp/{path}', headers={'Accept': 'text/html'})).text
        pages = await asyncio.gather(*(html(f'releases?page={page}') for page in range(1, 4)))
        tags = sorted({tag for page in pages for tag in _release_tags(page)}, key=lambda t: int(t[1:]), reverse=True)[:30]
        releases = []
        for offset in range(0, len(tags), 4):
            batch = tags[offset:offset+4]
            manifests = await asyncio.gather(*(html(f'releases/expanded_assets/{tag}') for tag in batch))
            for tag, source in zip(batch, manifests):
                release = _release_from_assets(tag, source)
                for asset in release['assets']:
                    asset['browser_download_url'] = f"https://github.com/ggml-org/llama.cpp/releases/download/{tag}/{asset['name']}"
                releases.append(release)
        return releases

    async def _prepare(self, job):
        folder = self.directory / job['id']
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60, read=120), headers={'User-Agent': 'NeveAI-Updater', 'Accept': 'application/vnd.github+json'}) as client:
                packages = []
                if 'neve' in job['targets']:
                    release = await self._neve_release(client)
                    tag = release.get('tag_name', '')
                    if not re.fullmatch(r'v?\d+(?:\.\d+)+(?:[-+][\w.-]+)?', tag):
                        raise ValueError('Versão do NeveAI inválida.')
                    from packaging.version import Version
                    current_file = self.root / 'version.txt'
                    if current_file.exists() and Version(tag.lstrip('v')) <= Version(current_file.read_text(encoding='utf-8-sig').strip().lstrip('v')):
                        raise ValueError('O NeveAI ja esta nesta versao ou em uma versao mais recente.')
                    job['versions']['neve'] = tag
                    job['neve'] = {'tag': tag, 'url': release['zipball_url']}
                    packages.append({'file': 'neve.zip', 'url': release['zipball_url']})
                if 'llama' in job['targets']:
                    version_file = self.root / 'llamacpp-server/version.txt'
                    lines = version_file.read_text(encoding='utf-8-sig').splitlines() if version_file.exists() else []
                    backend = installed_backend({'backend': lines[1] if len(lines) > 1 else '', 'asset': lines[2] if len(lines) > 2 else ''}) or 'cpu'
                    releases = await self._llama_releases(client)
                    selected = None
                    for release in releases:
                        tag = release.get('tag_name', '')
                        if release.get('draft') or not re.fullmatch(r'b\d+', tag):
                            continue
                        for asset in release.get('assets', []):
                            match = re.fullmatch(rf'llama-{re.escape(tag)}-bin-win-(.+)-x64\.zip', asset.get('name', ''))
                            if match and compatible_backend(backend, match[1]):
                                selected = release, asset, match[1]
                                break
                        if selected:
                            break
                    if not selected:
                        raise ValueError('Não foi encontrado um pacote llama.cpp compatível com a instalação.')
                    release, asset, backend = selected
                    if lines and re.fullmatch(r'b\d+', lines[0].strip()) and int(release['tag_name'][1:]) <= int(lines[0].strip()[1:]):
                        raise ValueError('O llama.cpp ja esta nesta versao ou em uma versao mais recente.')
                    job['versions']['llama'] = release['tag_name']
                    job['llama'] = {'release': release, 'backend': backend}
                    packages.append({'file': 'llama.zip', 'url': asset['browser_download_url'], 'digest': asset.get('digest')})
                    if backend.startswith('cuda'):
                        runtime = next((a for a in release['assets'] if a['name'] == f'cudart-llama-bin-win-{backend}-x64.zip'), None)
                        if runtime:
                            packages.append({'file': 'runtime.zip', 'url': runtime['browser_download_url'], 'digest': runtime.get('digest')})
                if shutil.disk_usage(folder).free < 2 * 1024**3:
                    raise ValueError('Libere pelo menos 2 GB de espaço para preparar a atualização.')
                for index, package in enumerate(packages):
                    job['phase'] = f"Baixando {package['file']}"
                    def progress(fraction):
                        job['progress'] = max(job.get('progress', 0), min(99, round((index + fraction) / len(packages) * 100)))
                        self._write(job)
                    destination = folder / package['file']
                    sha, size = await self._download(client, package['url'], destination, progress)
                    if (package.get('digest') or '').startswith('sha256:') and sha != package['digest'][7:]:
                        raise ValueError('A assinatura do pacote baixado não corresponde à release.')
                    job['phase'] = 'Verificando pacote'
                    self._write(job)
                    await asyncio.to_thread(validate_package, destination, package['file'])
                    job['packages'].append({**package, 'sha256': sha, 'size': size})
                job.update(status='ready', progress=100, phase='Pronto para reiniciar')
        except asyncio.CancelledError:
            job.update(status='failed', error='Download interrompido.')
            raise
        except Exception as error:
            job.update(status='failed', error=str(error), phase='Não foi possível concluir o download')
        finally:
            self._write(job)
            if job['status'] == 'failed':
                for path in folder.glob('*.zip'):
                    path.unlink(missing_ok=True)

    def restart(self, user_id):
        job = self.state(user_id)
        if job.get('status') != 'ready' or not re.fullmatch(r'[0-9a-f]{32}', job.get('id', '')):
            raise ValueError('Prepare o download antes de reiniciar.')
        manifest = self.directory / job['id'] / 'manifest.json'
        full = json.loads(manifest.read_text(encoding='utf-8'))
        if Path(full['root']).resolve() != self.root:
            raise ValueError('A atualização pertence a outra instalação.')
        executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        full['status'] = 'restarting'
        self._write(full)
        try:
            subprocess.Popen([str(executable), '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
                              '-File', str(self.root / 'launchers/iniciar.ps1'), '-UpdateJob', job['id']],
                             cwd=self.root, creationflags=0x08000000, close_fds=True)
        except OSError:
            full['status'] = 'ready'
            self._write(full)
            raise
        return {'status': 'restarting'}
