"""Memory-bounded encoding with the same model, precision and vector contract."""
import asyncio
import logging
import threading
import weakref

import psutil

log = logging.getLogger(__name__)
_locks = weakref.WeakKeyDictionary()
_guard = threading.Lock()


def batch_limit(requested):
    batch = min(128, max(32, int(requested)))
    try:
        available = psutil.virtual_memory().available
        if available < 1024**3:
            return min(batch, 4)
        if available < 3 * 1024**3:
            return min(batch, 8)
    except (OSError, AttributeError):
        return min(batch, 8)
    return batch


def _encode(model, values, batch, prefix):
    with _guard:
        lock = _locks.setdefault(model, threading.Lock())
    with lock:
        while True:
            try:
                return model.encode(values, batch_size=batch,
                                    **({"prompt": prefix} if prefix else {})).tolist()
            except (MemoryError, RuntimeError) as error:
                if batch <= 1 or (not isinstance(error, MemoryError) and not any(
                    term in str(error).lower() for term in ("out of memory", "can't allocate memory", "cannot allocate memory")
                )):
                    raise
                batch = max(1, batch // 2)
                log.warning("Embedding allocation failed; retrying with batch %s", batch)


async def encode_local(model, query, requested, prefix=None):
    batch = batch_limit(requested)
    if isinstance(query, str):
        return await asyncio.to_thread(_encode, model, query, batch, prefix)
    vectors = []
    # Release the model lock between bounded groups so queries can share the encoder.
    for start in range(0, len(query), batch * 4):
        vectors.extend(await asyncio.to_thread(
            _encode, model, query[start:start + batch * 4], batch, prefix
        ))
    return vectors
