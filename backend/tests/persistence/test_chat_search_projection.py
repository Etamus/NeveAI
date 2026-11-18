import importlib
from neveai.models.knowledge import Knowledge  # Register dependent tables before the database fixture.
from sqlalchemy import event, text
from neveai.internal.db import engine
from neveai.models.chats import ChatForm, Chats
from neveai.models.folders import Folder, Folders
from neveai.utils import chat_search_index as idx

migration = importlib.import_module("neveai.migrations.versions.f32d871b64cd_index_chat_search")


def test_projection_matches_like_and_never_hides_dirty_edits(monkeypatch, db):
    monkeypatch.setattr(idx, "schedule", lambda *args: None)
    def add(user, body):
        return Chats.insert_new_chat(user, ChatForm(chat={"title":"untitled", "messages":body,
            "history":{"messages":{"hidden":{"content":"other branch"}}}})).id
    a = add("u",[{"content":"Mixed Case BATATA ação 100%"},
                 {"content":[{"type":"text","text":"multimodal"}]}])
    b = add("u",[{"content":"unrelated"}, {"content":"ba"}, {"content":"tata"}])
    add("other",[{"content":"BATATA onlyForeign"}])
    queries = ("batata", "BATATA", "ação", "a", "100%", "_ata", "multimodal", "ba tata",
               "other branch", "unrelated", "onlyForeign", "pinned:false", "untitled")
    def find(q):
        return [row.id for row in Chats.get_chats_by_user_id_and_search_text("u", q, summaries_only=True)]
    before = {q:find(q) for q in queries}
    with engine.begin() as con:
        migration.install(con)
    try:
        assert before["batata"] == [a] and before["onlyForeign"] == []
        idx.warm(engine, "u")
        assert {q:find(q) for q in queries} == before
        Chats.update_chat_by_id(a, {"title":"untitled", "messages":[{"content":"changed"}]})
        assert find("changed") == [a] and find("batata") == []
        idx.warm(engine, "u")
        assert find("changed") == [a] and find("batata") == []
        with engine.begin() as con:
            con.execute(text("DELETE FROM chat WHERE id=:id"), {"id":a})
        assert find("changed") == [] and find("unrelated") == [b]
        with engine.connect() as con:
            assert not con.execute(text("SELECT 1 FROM chat_search_row WHERE chat_id=:id"), {"id":a}).first()
    finally:
        with engine.begin() as con:
            monkeypatch.setattr(migration.op, "get_bind", lambda:con)
            migration.downgrade()


def test_folder_summaries_read_no_documents_and_never_write(db):
    for fid, parent, owner in [("a",None,"u"),("b","a","u"),("c","missing","u"),("foreign",None,"v")]:
        db.add(Folder(id=fid,parent_id=parent,user_id=owner,name=fid,created_at=1,updated_at=17,
                      data={"files":[{"type":"file","id":"missing"}]}))
    db.commit()
    sql = []
    def record(conn,cursor,statement,*args):
        sql.append(statement)
    event.listen(engine, "before_cursor_execute", record)
    try:
        summaries = Folders.list_summaries("u", db)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert {r.id:r.parent_id for r in summaries} == {"a":None, "b":"a", "c":None}
    assert len(sql) == 1 and "folder.data" not in sql[0] and sql[0].startswith("SELECT")
    assert Folders.get_folder_by_id_and_user_id("c","u",db=db).data == {"files":[]}
    assert db.get(Folder,"c").data["files"] and db.get(Folder,"c").parent_id == "missing"
