"""Give chat and media work priority over the optional voice conversation."""

import asyncio
from contextlib import asynccontextmanager
from functools import wraps


class VoiceBusy(RuntimeError):
    pass


class _Lease:
    def __init__(self):
        self.stop = asyncio.Event()
        self.released = asyncio.Event()


_lease = None
_primary = 0


@asynccontextmanager
async def voice_slot():
    global _lease
    if _primary or _lease is not None:
        raise VoiceBusy
    lease = _lease = _Lease()
    try:
        yield lease.stop
    finally:
        _lease = None
        lease.released.set()


async def yield_voice():
    if (lease := _lease) is not None:
        lease.stop.set()
        await lease.released.wait()


@asynccontextmanager
async def primary_gpu_work():
    global _primary
    _primary += 1
    try:
        await yield_voice()
        yield
    finally:
        _primary -= 1


def prioritise_gpu_work(fn):
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        async with primary_gpu_work():
            return await fn(*args, **kwargs)

    return wrapped
