"""Scope local-model standby to the GPU work that actually needs its memory."""

import asyncio
from contextlib import asynccontextmanager


async def _finish_before_cancelling(operation):
    task = asyncio.ensure_future(operation)
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    return result


@asynccontextmanager
async def media_model_standby(model_manager, release_media):
    snapshot = None

    async def enter():
        nonlocal snapshot
        snapshot = await model_manager.standby()

    async def restore():
        # Do not replace a model explicitly loaded by the user during this job.
        if snapshot and not model_manager.get_loaded_model_id():
            await model_manager.resume(snapshot)

    try:
        # Capture the snapshot even if Stop arrives while unload is in flight.
        await _finish_before_cancelling(enter())
        yield
    finally:
        try:
            await _finish_before_cancelling(release_media())
        finally:
            await _finish_before_cancelling(restore())
