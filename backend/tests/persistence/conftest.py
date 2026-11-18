"""Run only against disposable storage, before importing application models."""

import os
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if "neveai.internal.db" in sys.modules:
    raise RuntimeError("Run this suite in a fresh process; database already imported")
STORAGE = tempfile.TemporaryDirectory(prefix="neveai-persistence-tests-")
os.environ.update(
    DATA_DIR=STORAGE.name,
    DATABASE_URL=f"sqlite:///{Path(STORAGE.name).as_posix()}/test.db",
    ENABLE_DB_MIGRATIONS="false",
    DATABASE_ENABLE_SQLITE_WAL="false",
    DATABASE_ENABLE_SESSION_SHARING="false",
    USE_CUDA_DOCKER="false",
)

from neveai.internal.db import Base, SessionLocal, engine
from neveai.models.chats import Chat, ChatMessage
from neveai.models.files import File


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    STORAGE.cleanup()
