"""Plan narrowly scoped local-model removals before changing files."""
import re
import shutil
import asyncio
import os
import tempfile
from pathlib import Path


async def import_model_stream(root: Path, filename: str, chunks) -> dict:
    if (not filename or len(filename) > 220 or any(c in filename for c in '<>:"/\\|?*')
            or any(ord(c) < 32 for c in filename) or filename.endswith((' ', '.'))
            or Path(filename).suffix.lower() != '.gguf'
            or filename.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
        raise ValueError('Selecione um arquivo GGUF com nome valido.')
    root = root.resolve(strict=True)
    destination = root / filename
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Ja existe um modelo com esse nome. O arquivo existente foi preservado.')
    fd, temporary_name = await asyncio.to_thread(tempfile.mkstemp, prefix='.model-import-', suffix='.part', dir=root)
    temporary = Path(temporary_name)
    header = bytearray()
    pending = bytearray()
    size = 0
    try:
        with os.fdopen(fd, 'wb') as target:
            async for chunk in chunks:
                if not chunk:
                    continue
                if len(header) < 24:
                    header.extend(chunk[:24 - len(header)])
                if len(header) >= 8 and (header[:4] != b'GGUF' or int.from_bytes(header[4:8], 'little') not in (2, 3)):
                    raise ValueError('O arquivo selecionado nao possui um cabecalho GGUF valido.')
                pending.extend(chunk)
                if len(pending) >= 1024 * 1024:
                    await asyncio.to_thread(target.write, pending)
                    pending.clear()
                size += len(chunk)
            if len(header) < 24:
                raise ValueError('O arquivo GGUF esta vazio ou incompleto.')
            if pending:
                await asyncio.to_thread(target.write, pending)
            await asyncio.to_thread(target.flush)
            await asyncio.to_thread(os.fsync, target.fileno())
        # Publish only a complete file, without replacing a concurrently imported model.
        await asyncio.to_thread(os.link, temporary, destination)
        return {'filename': filename, 'file_size': size}
    finally:
        temporary.unlink(missing_ok=True)


def project_storage(root: Path) -> dict:
    try:
        total, used, free = shutil.disk_usage(root.resolve())
        return {"available": True, "total": total, "used": used, "free": free}
    except OSError:
        return {"available": False, "total": 0, "used": 0, "free": 0}


def model_removal_paths(root: Path, filename: str) -> list[Path]:
    if not filename or '/' in filename or '\\' in filename or ':' in filename or Path(filename).suffix.lower() != '.gguf':
        raise ValueError('Invalid local model filename')
    root = root.resolve()
    selected = root / filename
    if selected.is_symlink() or selected.resolve().parent != root:
        raise ValueError('Model path leaves the models directory')
    if not selected.is_file():
        raise FileNotFoundError(filename)
    shard = re.fullmatch(r'(.+)-(\d{5})-of-(\d{5})\.gguf', filename, re.IGNORECASE)
    if not shard:
        return [selected]
    pattern = re.compile(re.escape(shard[1]) + r'-\d{5}-of-' + re.escape(shard[3]) + r'\.gguf', re.IGNORECASE)
    paths = sorted(path for path in root.iterdir() if pattern.fullmatch(path.name) and path.is_file())
    if any(path.is_symlink() or path.resolve().parent != root for path in paths):
        raise ValueError('Model shard leaves the models directory')
    return paths
