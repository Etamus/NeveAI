"""SHA-verified media assets; a warm installation only reads local files."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from huggingface_hub import hf_hub_download


def _verified(path, size, sha, *, downloaded=False):
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False
    if stat.st_size != size:
        return False
    stamp = [sha, size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino]
    marker = path.with_name("." + path.name + ".verified.json")
    with path.open("rb") as stream:
        # Sample large local weights so a coarse filesystem timestamp is not the
        # only signal. Newly downloaded files and small local files are always hashed.
        if size > 1024 * 1024:
            sample = hashlib.blake2s()
            for offset in (0, size // 2, size - 4096):
                stream.seek(offset)
                sample.update(stream.read(4096))
            stamp.append(sample.hexdigest())
            if not downloaded:
                try:
                    if json.loads(marker.read_text()) == stamp:
                        return True
                except (OSError, ValueError):
                    pass
            stream.seek(0)
        if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
            try:
                marker.unlink(missing_ok=True)
            except OSError:
                pass
            return False
    if size <= 1024 * 1024:
        return True
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as out:
            temp = Path(out.name)
            json.dump(stamp, out)
        os.replace(temp, marker)
    except OSError:
        pass  # Read-only local installations still work.
    finally:
        if temp and temp.exists():
            temp.unlink(missing_ok=True)
    return True


def ensure_pinned_asset(directory, filename, size, sha, sources):
    directory = Path(directory)
    target = directory / filename
    if _verified(target, size, sha):
        return target
    last = None
    for repo, revision in sources:
        try:
            hf_hub_download(repo_id=repo, filename=filename, revision=revision,
                            local_dir=str(directory), force_download=target.exists())
            if _verified(target, size, sha, downloaded=True):
                return target
            last = ValueError("SHA-256 diferente do esperado")
        except (OSError, RuntimeError, ValueError) as exc:
            last = exc
        except Exception as exc:
            from httpx import HTTPError
            from huggingface_hub.errors import HfHubHTTPError
            if not isinstance(exc, (HTTPError, HfHubHTTPError)):
                raise
            last = exc
    raise RuntimeError(f"Nao foi possivel verificar o peso {filename}.") from last
