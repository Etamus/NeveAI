"""Validate real routing and URL evidence, preserving user conversations and model state."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import requests
import socketio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.retrieval.web.url_identity import matches_requested_resource, canonical_url

BASE = "http://127.0.0.1:8080"
POST = "https://www.reddit.com/r/ECE/comments/1rphq0l/free_stuff_you_can_claim_with_your_student_email/"
DIRTY = POST + "?solution=cfb52a9b9938cf16&js_challenge=1&jsc_token=temporary&jsc_orig_r=&tl=pt-br"
USER_CHATS = ["a64d4d26-f6c8-4d60-8a4e-c099d97d47b8", "516ec90c-8faa-4753-99c2-d4eb4bb0b313"]
session, socket = requests.Session(), socketio.Client()
created, tasks, events, completed, results = [], [], {}, {}, []
test_model = None


def api(method, path, **kwargs):
    response = session.request(method, BASE + path, timeout=180, **kwargs)
    response.raise_for_status()
    return response


def fingerprint(identifier):
    chat = api("GET", "/api/v1/chats/" + identifier).json()["chat"]
    return hashlib.sha256(json.dumps(chat, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@socket.on("events")
def receive(packet):
    identifier = packet.get("chat_id")
    if identifier not in events:
        return
    event = packet.get("data", {})
    events[identifier].append(event)
    if (event.get("type") == "chat:completion" and event.get("data", {}).get("done")) or event.get("type") == "chat:message:error":
        completed[identifier].set()


def chat_case(label, messages, expected_search):
    history = {f"m{i}": {**message, "id": f"m{i}", "parentId": f"m{i-1}" if i else None,
               "childrenIds": [f"m{i+1}"] if i<len(messages)-1 else ["answer"], "done": True}
               for i, message in enumerate(messages)}
    parent = f"m{len(messages)-1}"
    history["answer"] = {"id":"answer", "role":"assistant", "content":"", "parentId":parent,
                         "childrenIds":[], "done":False, "model":model}
    identifier = api("POST", "/api/v1/chats/new", json={"chat": {
        "title":"Temporary web-source validation: " + label, "models":[model],
        "history":{"currentId":"answer","messages":history}, "messages":list(history.values()),
        "params":{}, "timestamp":int(time.time()*1000)}}).json()["id"]
    created.append(identifier)
    events[identifier], completed[identifier] = [], threading.Event()
    start = time.monotonic()
    response = api("POST", "/api/chat/completions", json={
        "model":model, "messages":messages, "stream":True, "features":{"web_search":True},
        "chat_id":identifier, "id":"answer", "parent_id":parent, "parent_message":history[parent],
        "session_id":socket.get_sid(),
        "background_tasks":{"title_generation":False,"tags_generation":False,"follow_up_generation":False},
        "params":{"reasoning_mode":"quick","no_think":True,"max_tokens":1536,"function_calling":"default"},
    }).json()
    if response.get("task_id"):
        tasks.append(response["task_id"])
    assert completed[identifier].wait(180), (label,"timeout")
    time.sleep(.2)
    answer = api("GET", "/api/v1/chats/" + identifier).json()["chat"]["history"]["messages"]["answer"]
    assert not answer.get("error"), (label,answer.get("error"))
    statuses = [event["data"] for event in events[identifier] if event.get("type")=="status"]
    searched = any(status.get("action")=="web_search" for status in statuses)
    assert searched is expected_search, (label,statuses)
    if expected_search:
        assert answer.get("sources"), (label,"missing evidence",answer["content"][:500])
    result = {"case":label,"seconds":round(time.monotonic()-start,2), "searched":searched,
              "queries":[status.get("queries") for status in statuses if status.get("action")=="web_search_queries_generated"],
              "sources":[meta.get("source") for source in answer.get("sources",[]) for meta in source.get("metadata",[])],
              "answer":answer["content"]}
    results.append(result)
    print(json.dumps({key:value for key,value in result.items() if key!="answer"}),flush=True)
    return answer


try:
    assert not api("GET", "/api/tasks").json()["tasks"], "Active user generation"
    originals = {identifier:fingerprint(identifier) for identifier in USER_CHATS}
    loaded = api("GET", "/llamacpp/models/loaded").json()["models"]
    if "--restart" in sys.argv:
        subprocess.run([sys.executable,str(ROOT / "scripts/restart_neve_backend.py")],check=True,cwd=ROOT)
    current = api("GET", "/llamacpp/models/loaded").json()["models"]
    if not current:
        candidate = loaded[0] if loaded else next(item for item in api("GET", "/llamacpp/models").json()["models"]
                                                  if "Qwen3.5" in item["filename"] and "9B" in item["filename"])
        payload = {key:candidate[key] for key in ("filename","n_ctx","n_gpu_layers","cache_type","context_shift","speculative_decoding","token_prediction") if key in candidate}
        payload.setdefault("n_ctx",8192)
        payload.setdefault("n_gpu_layers",-1)
        response = api("POST", "/llamacpp/models/load", json=payload).json()
        model = response.get("id") or candidate["id"]
        if not loaded:
            test_model = model
    else:
        model = current[0]["id"]
    user = api("GET", "/api/v1/auths/").json()
    session.headers["Authorization"] = "Bearer " + user["token"]
    socket.connect(BASE,socketio_path="ws/socket.io",auth={"token":user["token"]},transports=["websocket"])
    start = time.monotonic()
    evidence = api("POST", "/api/v1/retrieval/process/web/search", json={
        "urls":[DIRTY],"queries":[canonical_url(DIRTY)],"question":"O que esse link fala? " + DIRTY}).json()
    assert evidence["status"] and evidence["pages_read_count"]>0 and not evidence["unread_urls"]
    assert all(matches_requested_resource(doc["metadata"]["source"],[POST]) for doc in evidence["docs"])
    content = "\n".join(doc["content"] for doc in evidence["docs"])
    assert "GitHub" in content and "Student" in content and "JetBrains" in content
    results.append({"case":"direct-reddit-reader","seconds":round(time.monotonic()-start,2),
                    "metadata":[doc["metadata"] for doc in evidence["docs"]]})
    first = "Qual a cidade mais divertida da franca?"
    france = chat_case("subjective-travel",[{"role":"user","content":first}],True)
    chat_case("comparative-followup",[{"role":"user","content":first},
        {"role":"assistant","content":france["content"]},{"role":"user","content":"Tem alguma mais divertida?"}],True)
    chat_case("different-domain",[{"role":"user","content":"Qual camera tem o autofoco mais confiavel para fotografar esportes?"}],True)
    chat_case("self-contained-writing",[{"role":"user","content":"Crie um poema curto sobre uma cidade divertida, sem pesquisar."}],False)
    chat_case("self-contained-comparison",[{"role":"user","content":"Qual a frase mais longa deste texto? Texto: Oi. Esta frase tem muito mais palavras."}],False)
    reddit = chat_case("specific-reddit-post",[{"role":"user","content":"O que esse link fala? " + DIRTY}],True)
    source_text = "\n".join(str(doc) for source in reddit["sources"] for doc in source.get("document",[]))
    assert "GitHub" in source_text and "JetBrains" in source_text
    assert all(matches_requested_resource(meta["source"],[POST])
               for source in reddit["sources"] for meta in source.get("metadata",[]))
    assert "github" in reddit["content"].lower() or "estudant" in reddit["content"].lower()
    assert originals == {identifier:fingerprint(identifier) for identifier in USER_CHATS}, "User chat changed"
    results.append({"case":"user-chats-preserved","passed":True})
finally:
    for task in tasks:
        session.post(BASE + "/api/tasks/stop/" + task,timeout=15)
    for identifier in created:
        api("DELETE", "/api/v1/chats/" + identifier)
    if test_model:
        api("POST", "/llamacpp/models/unload",json={"model_id":test_model})
    if socket.connected:
        socket.disconnect()
    (ROOT / "logs/web-intent-sources-live.json").write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
