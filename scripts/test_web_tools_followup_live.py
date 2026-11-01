"""Real Qwen + chat pipeline, using disposable chats and the original read-only PDF."""
import json
from pathlib import Path
import threading
import time
import uuid

import requests
import socketio
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs/web-tools-followup-live"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8080"
MODEL = "local/Qwen3.5 9B MTP UDQ4_K_XL"
session = requests.Session()
socket = socketio.Client()
events = {}
finished = {}
created_chats = []
created_files = set()
results = []


def api(method, path, **kwargs):
    response = session.request(method, BASE + path, timeout=240, **kwargs)
    response.raise_for_status()
    return response


@socket.on("events")
def receive(packet):
    chat = packet.get("chat_id")
    if chat not in events:
        return
    event = packet.get("data", {})
    events[chat].append(event)
    if event.get("type") == "chat:message:files":
        created_files.update(item["id"] for item in event.get("data", {}).get("files", []))
    if (event.get("type") == "chat:completion" and event.get("data", {}).get("done")) or event.get("type") == "chat:message:error":
        finished[chat].set()


def run(label, messages, features, files=None, native=False):
    history = {}
    for index, message in enumerate(messages):
        history[f"m{index}"] = {**message, "id": f"m{index}", "parentId": f"m{index-1}" if index else None,
                                 "childrenIds": [f"m{index+1}"] if index < len(messages)-1 else ["answer"], "done": True}
    last = f"m{len(messages)-1}"
    history["answer"] = {"id":"answer", "role":"assistant", "content":"", "parentId":last,
                         "childrenIds":[], "done":False, "model":MODEL}
    chat = api("POST", "/api/v1/chats/new", json={"chat":{
        "title":"Temporary validation: "+label, "models":[MODEL], "history":{"currentId":"answer","messages":history},
        "messages":list(history.values()), "params":{}, "timestamp":int(time.time()*1000)}}).json()["id"]
    created_chats.append(chat)
    events[chat] = []
    finished[chat] = threading.Event()
    started = time.monotonic()
    response = api("POST", "/api/chat/completions", json={
        "model":MODEL,"messages":messages,"stream":True,"features":features,"files":files or [],
        "chat_id":chat,"id":"answer","parent_id":last,"parent_message":history[last],
        "session_id":socket.get_sid(), "background_tasks":{"title_generation":False,"tags_generation":False,"follow_up_generation":False},
        "params":{"reasoning_mode":"quick","no_think":True,"max_tokens":1024,
                  "function_calling":"native" if native else "default"},
    }).json()
    try:
        assert finished[chat].wait(240), (label, response)
        time.sleep(0.3)
        record = api("GET", "/api/v1/chats/"+chat).json()["chat"]["history"]["messages"]["answer"]
        created_files.update(item["id"] for item in record.get("files", []))
        result = {"case":label, "seconds":round(time.monotonic()-started,2), "content":record.get("content"),
                  "statuses":[event["data"] for event in events[chat] if event.get("type")=="status"],
                  "files":record.get("files",[]), "sources":record.get("sources",[]), "error":record.get("error")}
        (OUT / f"{label}.json").write_text(json.dumps({"result":result,"events":events[chat]},indent=2,ensure_ascii=False),encoding="utf-8")
        results.append(result)
        print(json.dumps({key:value for key,value in result.items() if key not in {"files","sources","content"}},ensure_ascii=True),flush=True)
        assert not result["error"], result
        return result
    finally:
        task_id = response.get("task_id")
        if not finished[chat].is_set() and task_id:
            api("POST", "/api/tasks/stop/"+task_id)


try:
    assert not api("GET", "/api/tasks").json()["tasks"]
    user = api("GET", "/api/v1/auths/").json()
    socket.connect(BASE, socketio_path="ws/socket.io", auth={"token":user["token"]}, transports=["websocket"])
    source_id = "a89040f9-dda3-43b5-8872-ce37e22525cd"
    source = api("GET", "/api/v1/files/"+source_id).json()
    attachment = {"id":source_id,"type":"file","name":source.get("filename") or source.get("name"),"file":source}

    edited = run("remove-last-paragraph", [{"role":"user","content":"Remova o ultimo paragrafo","files":[attachment]}], {"file_generation":True}, [attachment])
    assert len(edited["files"])==1, edited
    newfile=edited["files"][0]
    data=api("GET",f"/api/v1/files/{newfile['id']}/content").content
    (OUT / "edited-live.pdf").write_bytes(data)
    with pymupdf.open(stream=data,filetype="pdf") as document:
        assert len(document)==2
        assert "Inicialmente, Axel" not in document[1].get_text()
        assert "acidentalmente" in document[1].get_text()

    thanks=run("thanks-after-document", [
        {"role":"user","content":"Remova o ultimo paragrafo"},
        {"role":"assistant","content":"O arquivo foi preparado e ja pode ser baixado.","files":[newfile]},
        {"role":"user","content":"Obrigado!"},
    ], {"file_generation":True}, [newfile])
    assert not thanks["files"]
    assert not any(status.get("action")=="file_generation" for status in thanks["statuses"])
    assert "possivel preparar" not in (thanks["content"] or "")

    for native in [False, True]:
        web=run("got-web-native" if native else "got-web", [{"role":"user","content":"Qual a melhor temporada de GOT?"}], {"web_search":True}, native=native)
        assert any(status.get("action")=="web_search" for status in web["statuses"]), web
        assert web["sources"], web

    combined=run("got-web-document",[{"role":"user","content":"Crie um PDF curto: qual a melhor temporada de GOT? Inclua fontes."}],{"web_search":True,"file_generation":True})
    assert combined["files"], combined
    assert any(status.get("action")=="web_search" for status in combined["statuses"])
    data=api("GET", f"/api/v1/files/{combined['files'][0]['id']}/content").content
    (OUT / "web-document.pdf").write_bytes(data)
    with pymupdf.open(stream=data,filetype="pdf") as document:
        text="\n".join(page.get_text() for page in document)
        assert "Game of Thrones" in text and len(text)>300
        assert "quantidade de tokens" not in text
        document[0].get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(OUT / "web-document.png")

    plain=run("plain-pdf",[{"role":"user","content":"Faca um pdf sobre batats. Escreva tres paragrafos curtos."}],{"file_generation":True})
    assert len(plain["files"])==1, plain
    attached=plain["files"][0]
    previous=api("GET", f"/api/v1/files/{attached['id']}/content").content
    (OUT / "plain-before.pdf").write_bytes(previous)
    followup=run("delete-from-previous-document",[
        {"role":"user","content":"Faca um pdf sobre batats. Escreva tres paragrafos curtos."},
        {"role":"assistant","content":"O arquivo foi preparado e ja pode ser baixado.","files":[attached]},
        {"role":"user","content":"Remova o ultimo paragrafo"},
    ],{"file_generation":True},[attached])
    assert len(followup["files"])==1, followup
    revised=api("GET", f"/api/v1/files/{followup['files'][0]['id']}/content").content
    (OUT / "plain-after.pdf").write_bytes(revised)
    with pymupdf.open(stream=previous,filetype="pdf") as before, pymupdf.open(stream=revised,filetype="pdf") as after:
        before_text="\n".join(page.get_text() for page in before)
        after_text="\n".join(page.get_text() for page in after)
        assert len(before)==len(after)
        assert 0 < len(after_text.strip()) < len(before_text.strip())
finally:
    # Only IDs returned by these disposable requests are eligible for cleanup.
    for chat in created_chats:
        api("DELETE", "/api/v1/chats/"+chat)
    for file in created_files:
        assert file != "a89040f9-dda3-43b5-8872-ce37e22525cd"
        api("DELETE", "/api/v1/files/"+file)
    socket.disconnect()
    (OUT / "summary.json").write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
