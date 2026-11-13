"""Inspect embedded NextN heads without reading model weight data into RAM."""

from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

_unavailable = OrderedDict()


def _identity(path):
    path = Path(path)
    stat = path.stat()
    return str(path.resolve()), stat.st_size, stat.st_mtime_ns


@lru_cache(maxsize=32)
def _has_mtp(identity):
    from gguf import GGUFReader

    reader = GGUFReader(identity[0], 'r')
    return any(key.endswith('.nextn_predict_layers') and int(field.contents()) > 0
               for key, field in reader.fields.items())


def supports_embedded_mtp(model, runtime):
    try:
        identity = (_identity(model), _identity(runtime))
        return identity not in _unavailable and _has_mtp(identity[0])
    except (ImportError, OSError, ValueError, TypeError, IndexError, KeyError):
        return False


def mark_mtp_unavailable(model, runtime):
    try:
        identity = (_identity(model), _identity(runtime))
        _unavailable[identity] = True
        while len(_unavailable) > 32:
            _unavailable.popitem(last=False)
    except OSError:
        pass
