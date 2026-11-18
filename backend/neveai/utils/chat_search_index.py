"""SQLite substring search; a stale or absent index must never hide a live edit."""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chat-search-index")
_lock = threading.Lock()
_pending = set()

DIRECT = """EXISTS (SELECT 1 FROM json_each(chat.chat,'$.messages') AS m
            WHERE LOWER(m.value->>'content') LIKE '%' || :content_key || '%')"""
INDEXED = """chat.id IN (SELECT r.chat_id FROM chat_search_fts f
            JOIN chat_search_row r ON r.id=f.rowid WHERE f.body LIKE '%' || :content_key || '%')"""


def warm(engine, user_id, limit=8):
    with engine.connect() as con:
        ids = con.execute(text("SELECT chat_id FROM chat_search_dirty WHERE user_id=:u LIMIT :n"),
                          {"u": user_id, "n": limit}).scalars().all()
    for chat_id in ids:
        with engine.begin() as con:
            # Reserve the writer only for this chat. Read the current snapshot inside
            # that transaction; a concurrent edit either precedes this or marks it dirty again.
            con.execute(text("DELETE FROM chat_search_row WHERE chat_id=:id"), {"id": chat_id})
            con.execute(text("""INSERT INTO chat_search_row(chat_id,body)
                SELECT chat.id, LOWER(m.value->>'content') FROM chat,json_each(chat.chat,'$.messages') m
                WHERE chat.id=:id AND m.type='object' AND m.value->>'content' IS NOT NULL"""), {"id": chat_id})
            con.execute(text("DELETE FROM chat_search_dirty WHERE chat_id=:id"), {"id": chat_id})


def schedule(engine, user_id):
    key = (engine, user_id)
    with _lock:
        if key in _pending or len(_pending) >= 4:
            return
        _pending.add(key)
    def work():
        try:
            warm(engine, user_id)
        except SQLAlchemyError:
            log.debug("Chat search index postponed", exc_info=True)
        finally:
            with _lock:
                _pending.discard(key)
    _pool.submit(work)


def content_clause(db, user_id):
    # Deployments that disable migrations or lack FTS5 retain the original query.
    if not db.execute(text("SELECT 1 FROM sqlite_master WHERE name='chat_search_dirty'")).scalar():
        return DIRECT
    if db.execute(text("SELECT 1 FROM chat_search_dirty WHERE user_id=:u LIMIT 1"), {"u": user_id}).scalar():
        engine = db.get_bind()
        if getattr(engine, "url", None) and engine.url.database not in (None, "", ":memory:"):
            schedule(engine, user_id)
    # Check dirty state in the SAME statement as the matches, including when clean above.
    return f"CASE WHEN EXISTS (SELECT 1 FROM chat_search_dirty d WHERE d.chat_id=chat.id) THEN {DIRECT} ELSE {INDEXED} END"
