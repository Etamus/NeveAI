"""Validate web-provider recovery through a disposable real chat."""
import json
import threading
import time
import uuid
from pathlib import Path

import requests
import socketio

BASE = "http://127.0.0.1:8080"
session = requests.Session()
socket = socketio.Client()
finished = threading.Event()
events = []
chat_id = None
task_id = None


def api(method, path, **kwargs):
    response = session.request(method, BASE + path, timeout=180, **kwargs)
    response.raise_for_status()
    return response.json()


@socket.on("events")
def receive(packet):
    if packet.get("chat_id") != chat_id:
        return
    event = packet.get("data", {})
    events.append(event)
    if (event.get("type") == "chat:completion" and event.get("data", {}).get("done")) or event.get("type") == "chat:message:error":
        finished.set()


try:
    assert not api("GET", "/api/tasks")["tasks"]
    model = api("GET", "/llamacpp/models/loaded")["models"][0]["id"]
    user = api("GET", "/api/v1/auths/")
    socket.connect(BASE, socketio_path="ws/socket.io", auth={"token": user["token"]}, transports=["websocket"])
    messages = [
        {"role": "user", "content": "Boa tarde"},
        {"role": "assistant", "content": "Boa tarde! Como posso ajudar?"},
        {"role": "user", "content": "Qual a melhor temporada de GOT?"},
    ]
    history = {
        f"m{i}": {**message, "id": f"m{i}", "parentId": f"m{i-1}" if i else None,
                   "childrenIds": [f"m{i+1}" if i < 2 else "answer"], "done": True}
        for i, message in enumerate(messages)
    }
    history["answer"] = {"id": "answer", "parentId": "m2", "childrenIds": [], "role": "assistant", "content": "", "done": False, "model": model}
    chat_id = api("POST", "/api/v1/chats/new", json={"chat": {
        "title": "Temporary web recovery " + uuid.uuid4().hex[:8], "models": [model],
        "history": {"currentId": "answer", "messages": history}, "messages": list(history.values()), "params": {},
    }})["id"]
    started = time.monotonic()
    task_id = api("POST", "/api/chat/completions", json={
        "model": model, "messages": messages, "stream": True, "features": {"web_search": True},
        "chat_id": chat_id, "id": "answer", "parent_id": "m2", "parent_message": history["m2"],
        "session_id": socket.get_sid(), "background_tasks": {"title_generation": False, "tags_generation": False, "follow_up_generation": False},
        "params": {"reasoning_mode": "quick", "no_think": True, "max_tokens": 1024, "function_calling": "default"},
    }).get("task_id")
    assert finished.wait(180), "Real generation timed out"
    time.sleep(0.4)
    answer = api("GET", "/api/v1/chats/" + chat_id)["chat"]["history"]["messages"]["answer"]
    statuses = [event.get("data") for event in events if event.get("type") == "status"]
    result = {"seconds": round(time.monotonic()-started, 2), "statuses": statuses, "answer": answer}
    output = Path(__file__).resolve().parents[1] / "logs/web-recovery-live.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"seconds": result["seconds"], "statuses": statuses, "sources": len(answer.get("sources", [])), "error": answer.get("error")}, ensure_ascii=True), flush=True)
    assert not answer.get("error"), answer.get("error")
    assert answer.get("sources"), "Real response has no sources"
    assert not any("Nenhum resultado" in str(status) for status in statuses), statuses
    assert answer.get("content", "").strip(), "Empty real response"
finally:
    if task_id and not finished.is_set():
        api("POST", "/api/tasks/stop/" + task_id)
    if chat_id:
        api("DELETE", "/api/v1/chats/" + chat_id)
    if socket.connected:
        socket.disconnect()
