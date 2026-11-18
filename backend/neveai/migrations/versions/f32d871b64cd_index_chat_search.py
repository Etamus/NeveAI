"""Index the visible transcript lazily, without parsing chats on startup or during streaming."""
from alembic import op
from sqlalchemy.exc import OperationalError

revision = "f32d871b64cd"
down_revision = "d8a91f02c631"
branch_labels = None
depends_on = None


def install(connection):
    if connection.dialect.name != "sqlite":
        return
    try:
        connection.exec_driver_sql("CREATE VIRTUAL TABLE chat_search_fts USING fts5(body, content='chat_search_row', content_rowid='id', tokenize='trigram')")
    except OperationalError as exc:
        if "no such module" in str(exc) or "no such tokenizer" in str(exc):
            return
        raise
    for sql in (
        "CREATE TABLE chat_search_row(id INTEGER PRIMARY KEY, chat_id TEXT NOT NULL, body TEXT NOT NULL)",
        "CREATE INDEX chat_search_row_owner ON chat_search_row(chat_id)",
        "CREATE TABLE chat_search_dirty(chat_id TEXT PRIMARY KEY, user_id TEXT)",
        "CREATE INDEX chat_search_dirty_user ON chat_search_dirty(user_id)",
        "CREATE TRIGGER chat_search_add AFTER INSERT ON chat_search_row BEGIN INSERT INTO chat_search_fts(rowid,body) VALUES(new.id,new.body); END",
        """CREATE TRIGGER chat_search_remove AFTER DELETE ON chat_search_row BEGIN
             INSERT INTO chat_search_fts(chat_search_fts,rowid,body) VALUES('delete',old.id,old.body); END""",
        "CREATE TRIGGER chat_search_new AFTER INSERT ON chat BEGIN INSERT OR REPLACE INTO chat_search_dirty VALUES(new.id,new.user_id); END",
        "CREATE TRIGGER chat_search_changed AFTER UPDATE OF chat,user_id ON chat BEGIN INSERT OR REPLACE INTO chat_search_dirty VALUES(new.id,new.user_id); END",
        """CREATE TRIGGER chat_search_deleted AFTER DELETE ON chat BEGIN
             DELETE FROM chat_search_row WHERE chat_id=old.id; DELETE FROM chat_search_dirty WHERE chat_id=old.id; END""",
        "INSERT INTO chat_search_dirty SELECT id,user_id FROM chat",
    ):
        connection.exec_driver_sql(sql)


def upgrade():
    install(op.get_bind())


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        for name in ("chat_search_deleted", "chat_search_changed", "chat_search_new", "chat_search_remove", "chat_search_add"):
            connection.exec_driver_sql("DROP TRIGGER IF EXISTS " + name)
        for name in ("chat_search_fts", "chat_search_row", "chat_search_dirty"):
            connection.exec_driver_sql("DROP TABLE IF EXISTS " + name)
