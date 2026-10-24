"""Scheduling helpers without application or database imports."""

import asyncio
from contextlib import suppress


async def run_sync_chat_operation(operation, *args):
    """Run a complete model operation; its session stays inside the worker.

    Join an in-flight write before cancellation can trigger a partial-state save.
    Callers must not pass sessions or mutate arguments until this returns.
    """
    task = asyncio.create_task(asyncio.to_thread(operation, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(task)
        with suppress(Exception):
            task.result()
        raise


async def stream_with_flush_ticks(source, flush, interval=0.025):
    """Yield None on idle ticks without cancelling the upstream read.

    Closing, failure and cancellation flush accumulated state and join the read.
    """
    iterator = source.__aiter__()
    pending = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(iterator))
            ready, _ = await asyncio.wait({pending}, timeout=interval)
            if not ready:
                yield None
                continue
            try:
                item = pending.result()
            except StopAsyncIteration:
                break
            pending = None
            yield item
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pending
        try:
            await flush()
        finally:
            close = getattr(iterator, "aclose", None)
            if close is not None:
                await close()
