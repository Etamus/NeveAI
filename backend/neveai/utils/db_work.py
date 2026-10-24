"""Worker-local sessions for blocking route work and explicit transactions."""

from contextlib import contextmanager
from functools import wraps
from inspect import signature

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from neveai.internal.db import SessionLocal


@contextmanager
def transaction_context(db=None):
    # Explicit transaction participants must share a session even when the legacy
    # DATABASE_ENABLE_SESSION_SHARING optimization is disabled.
    if isinstance(db, Session):
        try:
            yield db
        except Exception:
            db.rollback()
            raise
    else:
        with SessionLocal() as session:
            yield session


def session_route(function):
    """Run a synchronous endpoint with a session owned by that same worker.

    Hide the internal db argument from FastAPI so no request dependency creates
    a session on a different thread. Shared non-route helpers stay undecorated.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        with SessionLocal() as db:
            return function(*args, **kwargs, db=db)

    wrapped.__signature__ = signature(function).replace(
        parameters=[p for p in signature(function).parameters.values() if p.name != "db"]
    )
    return wrapped


async def db_work(function, *args, **kwargs):
    def work():
        with SessionLocal() as db:
            return function(*args, **kwargs, db=db)

    return await run_in_threadpool(work)
