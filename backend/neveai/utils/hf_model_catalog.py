"""Bounded Hugging Face metadata cache and safe GGUF download plans."""
import asyncio
import hashlib
import json
import os
import re
import time
from collections import OrderedDict
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlsplit

import httpx


def validate_repo(repo):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', repo) or '..' in repo:
        raise ValueError('Repositorio Hugging Face invalido.')
    return repo


def validate_file(path):
    if (not path or len(path) > 500 or any(c in path for c in '\\:?*<>"|#%')
            or any(ord(c) < 32 for c in path) or path.startswith('/')
            or any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in path.split('/'))
            or not path.lower().endswith('.gguf')):
        raise ValueError('Arquivo GGUF invalido.')
    return path


def mainline_filename(repo, path):
    # Unsloth deliberately hides this alternate tensor layout from generic GGUF clients.
    if repo.lower() == 'unsloth/inkling-2-mini-gguf':
        if re.fullmatch(r'Mainline_Support/Inkling-2-Mini-[\w.-]+\.gguf_file', path):
            return validate_file(path[:-5])
        if 'mmproj' not in PurePosixPath(path).name.lower():
            raise ValueError('Este arquivo requer o runtime da Unsloth.')
    return validate_file(path)


def local_filename(repo, path):
    validate_repo(repo)
    path = mainline_filename(repo, path)
    directory = str(PurePosixPath(path).parent)
    folder = hashlib.sha256(directory.encode()).hexdigest()[:8] + '--' if directory != '.' else ''
    name = f"{repo.replace('/', '--')}--{folder}{PurePosixPath(path).name}"
    # Preserve shard suffixes so llama.cpp can discover the other parts.
    if len(name) > 180:
        name = hashlib.sha256((repo + directory).encode()).hexdigest()[:16] + '--' + PurePosixPath(path).name
    if len(name) > 220:
        raise ValueError('Nome do arquivo muito longo para importacao segura.')
    return name


def download_filename(repo, path, root, catalog_short=None):
    name = local_filename(repo, path)
    # Keep existing Neve installations and their model IDs; isolate arbitrary Hub filenames.
    if catalog_short and '/' not in path and catalog_short in path.lower() and not (root / name).exists():
        return path
    return name


def group_files(files, repo, models_dir, mmproj_dir, catalog_short=None):
    groups, encoders = {}, []
    for item in files:
        path = item.get('path', '')
        if item.get('type') != 'file':
            continue
        size = int(item.get('size') or (item.get('lfs') or {}).get('size') or 0)
        encoder = 'mmproj' in PurePosixPath(path).name.lower()
        root = mmproj_dir if encoder else models_dir
        try:
            name = download_filename(repo, path, root, catalog_short)
        except ValueError:
            continue
        destination = root / name
        installed = destination.is_file() and not destination.is_symlink() and size > 0 and destination.stat().st_size == size
        row = {'path': path, 'size': size, 'local_filename': name, 'installed': installed, 'files': [item]}
        shard = re.fullmatch(r'(.+)-(\d{5})-of-(\d{5})\.gguf', path, re.I)
        if encoder:
            encoders.append(row)
        elif shard:
            key = (shard[1], int(shard[3]))
            groups.setdefault(key, []).append((int(shard[2]), row))
        else:
            groups[(path, 1)] = [(1, row)]
    models = []
    for (_, count), parts in groups.items():
        parts.sort(key=lambda part: part[0])
        if count > 64 or [part[0] for part in parts] != list(range(1, count + 1)):
            continue
        rows = [part[1] for part in parts]
        models.append({**rows[0], 'size': sum(row['size'] for row in rows), 'parts': count,
                       'installed': all(row['installed'] for row in rows), 'files': [row['files'][0] for row in rows]})
    return sorted(models, key=lambda row: row['path'].lower()), sorted(encoders, key=lambda row: row['path'].lower())


class HuggingFaceCatalog:
    def __init__(self, transport=None):
        self.cache = OrderedDict()
        self.inflight = {}
        self.transport = transport
        self.cache_sizes = {}

    async def cached(self, key, loader):
        now = time.monotonic()
        if key in self.cache and now - self.cache[key][0] < 180:
            self.cache.move_to_end(key)
            return self.cache[key][1]
        if key not in self.inflight:
            async def fetch():
                try:
                    result = await loader()
                    size = len(json.dumps(result, ensure_ascii=False).encode())
                    if size <= 4 * 1024 * 1024:
                        self.cache[key] = (time.monotonic(), result)
                        self.cache_sizes[key] = size
                        self.cache.move_to_end(key)
                        while len(self.cache) > 32 or sum(self.cache_sizes.values()) > 4 * 1024 * 1024:
                            evicted, _ = self.cache.popitem(last=False)
                            self.cache_sizes.pop(evicted, None)
                    return result
                finally:
                    self.inflight.pop(key, None)
            self.inflight[key] = asyncio.create_task(fetch())
        return await asyncio.shield(self.inflight[key])

    async def request(self, path, params):
        token = os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN')
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        async with httpx.AsyncClient(timeout=12, transport=self.transport, headers=headers) as client:
            response = await client.get('https://huggingface.co' + path, params=params)
            response.raise_for_status()
            if len(response.content) > 8 * 1024 * 1024:
                raise ValueError('Metadados do repositorio excedem o limite seguro.')
            return response.json(), response.links.get('next', {}).get('url')

    @staticmethod
    def cursor(url):
        if not url:
            return None
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'huggingface.co':
            raise ValueError('Paginacao externa recusada.')
        return parse_qs(parsed.query).get('cursor', [None])[0]

    async def search(self, query='', cursor=None):
        if len(query) > 200 or cursor and len(cursor) > 4000:
            raise ValueError('Pesquisa muito longa.')
        async def load():
            if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', query.strip()) and '..' not in query and not cursor:
                repo = validate_repo(query.strip())
                try:
                    info, _ = await self.request(f'/api/models/{repo}', {})
                    return {'models': [{'id': repo, 'downloads': info.get('downloads', 0), 'likes': info.get('likes', 0), 'gated': bool(info.get('gated'))}], 'next_cursor': None}
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
            params = {'filter': 'gguf', 'pipeline_tag': 'text-generation', 'sort': 'downloads', 'direction': '-1', 'limit': '24'}
            if query.strip():
                params['search'] = query.strip()
            if cursor:
                params['cursor'] = cursor
            data, next_url = await self.request('/api/models', params)
            return {'models': [{'id': validate_repo(row['id']), 'downloads': row.get('downloads', 0),
                                'likes': row.get('likes', 0), 'gated': bool(row.get('gated'))}
                               for row in data if isinstance(row, dict) and not row.get('private')],
                    'next_cursor': self.cursor(next_url)}
        return await self.cached(('search', query.strip(), cursor), load)

    async def files(self, repo):
        validate_repo(repo)
        async def load():
            items, cursor = [], None
            for _ in range(4):
                params = {'recursive': 'true', 'limit': '1000'}
                if cursor:
                    params['cursor'] = cursor
                data, next_url = await self.request(f'/api/models/{repo}/tree/main', params)
                for row in data:
                    if not isinstance(row, dict) or row.get('type') != 'file' or not isinstance(row.get('path'), str):
                        continue
                    try:
                        mainline_filename(repo, row['path'])
                    except ValueError:
                        continue
                    items.append({'type': 'file', 'path': row['path'], 'size': row.get('size', 0),
                                  'lfs': {'oid': (row.get('lfs') or {}).get('oid')}})
                cursor = self.cursor(next_url)
                if not cursor:
                    break
            return {'files': items, 'truncated': bool(cursor)}
        return await self.cached(('files', repo), load)


hf_catalog = HuggingFaceCatalog()
