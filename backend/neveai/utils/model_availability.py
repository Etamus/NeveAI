"""Read-only notifications about the GPU media queue; never load/unload models."""

import asyncio
import logging
from uuid import uuid4


log = logging.getLogger(__name__)
_epoch = uuid4().hex
_revision = 0
_pending = 0
_notifications = set()


def get_model_availability():
    from neveai.routers.llamacpp import model_manager

    return {
        "epoch": _epoch,
        "revision": _revision,
        "busy": _pending > 0,
        "loaded_models": [] if _pending else model_manager.get_loaded_models(),
    }


async def _publish(state):
    try:
        from neveai.socket.main import sio, SESSION_POOL

        users = {entry["id"] for sid in list(SESSION_POOL.keys())
                 if (entry := SESSION_POOL.get(sid)) and entry.get("id")}
        for user_id in users:
            await sio.emit("model:availability", state, room=f"user:{user_id}")
    except Exception:
        log.exception("Could not publish model availability")


def _notify():
    try:
        state = get_model_availability()
        task = asyncio.get_running_loop().create_task(_publish(state))
        _notifications.add(task)
        task.add_done_callback(_notifications.discard)
    except Exception:
        # Observability must not change generation or cleanup semantics.
        log.exception("Could not observe model availability")


def media_job_queued():
    global _pending, _revision
    _pending += 1
    _revision += 1
    _notify()


def media_job_released():
    global _pending, _revision
    _pending = max(0, _pending - 1)
    _revision += 1
    _notify()
