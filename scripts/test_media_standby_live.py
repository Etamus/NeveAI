"""Authorized GPU checks through chat; delete only this test's chats/files."""
import json
import os
from pathlib import Path
import threading
import time

import requests
import socketio


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("NEVE_MEDIA_TEST_OUTPUT", "logs/media-standby-live")
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8080"
MODEL = "local/Qwen3.5 9B MTP UDQ4_K_XL"
session = requests.Session()
socket = socketio.Client()
events, completed = {}, {}
created_chats, created_files = [], set()
results = []


def api(method, path, **kwargs):
    response = session.request(method, BASE + path, timeout=180, **kwargs)
    response.raise_for_status()
    return response


def loaded():
    return api("GET", "/llamacpp/models/loaded").json()["models"]


@socket.on("events")
def receive(packet):
    chat = packet.get("chat_id")
    if chat not in events:
        return
    event = packet.get("data", {})
    events[chat].append(event)
    if event.get("type") in {"files", "chat:message:files"}:
        created_files.update(item["id"] for item in event.get("data", {}).get("files", []))
    if event.get("type") == "chat:completion" and event.get("data", {}).get("done"):
        completed[chat].set()


def run(label, features, cancel=False):
    before = loaded()
    assert len(before) == 1 and before[0]["id"] == MODEL, before
    message = {"id": "question", "role": "user", "content": "A red ceramic cup on a wooden table, soft daylight, fixed camera.",
               "parentId": None, "childrenIds": ["answer"], "models": [MODEL]}
    answer = {"id": "answer", "role": "assistant", "model": MODEL, "content": "", "done": False,
              "parentId": "question", "childrenIds": []}
    chat = api("POST", "/api/v1/chats/new", json={"chat": {
        "title": "Temporary standby validation: " + label, "models": [MODEL],
        "history": {"currentId": "answer", "messages": {"question": message, "answer": answer}},
        "messages": [message, answer], "params": {}, "timestamp": int(time.time()*1000)}}).json()["id"]
    created_chats.append(chat)
    events[chat], completed[chat] = [], threading.Event()
    start = time.monotonic()
    response = api("POST", "/api/chat/completions", json={
        "model": MODEL, "messages": [{"role": "user", "content": message["content"]}],
        "stream": True, "features": features, "chat_id": chat, "id": "answer", "parent_id": "question",
        "parent_message": message, "session_id": socket.get_sid(), "params": {},
        "background_tasks": {"title_generation": False, "tags_generation": False, "follow_up_generation": False}}).json()
    task_id = response.get("task_id")
    saw_standby = stopped = False
    try:
        deadline = start + 600
        restored = False
        while time.monotonic() < deadline:
            current = loaded()
            if not current:
                saw_standby = True
            if cancel and saw_standby and not stopped:
                time.sleep(1)
                api("POST", "/api/tasks/stop/" + task_id)
                stopped = True
            tasks = api("GET", "/api/tasks").json()["tasks"]
            if saw_standby and current and not tasks and (stopped or completed[chat].is_set()):
                restored = True
                break
            time.sleep(0.5)
        assert saw_standby and restored, {"label": label, "events": events[chat][-5:]}
        after = loaded()
        for key in ["id", "filename", "n_ctx", "n_gpu_layers", "cache_type", "speculative_decoding", "token_prediction", "context_shift", "mmproj_filename", "context_auto"]:
            assert before[0].get(key) == after[0].get(key), (key, before, after)
        record = api("GET", "/api/v1/chats/"+chat).json()["chat"]["history"]["messages"]["answer"]
        created_files.update(item["id"] for item in record.get("files", []))
        if not cancel:
            assert record.get("files") and not record.get("error"), record
            errors = [event for event in events[chat] if event.get("type") == "status" and event.get("data", {}).get("error")]
            assert not errors, errors
            for item in record["files"]:
                data = api("GET", f"/api/v1/files/{item['id']}/content").content
                (OUT / (label + (".mp4" if features.get("video_generation") else ".png"))).write_bytes(data)
        result = {"case": label, "seconds": round(time.monotonic()-start, 2), "standby": saw_standby,
                  "restored_same_parameters": True, "cancelled": stopped, "files": len(record.get("files", []))}
        results.append(result)
        (OUT / (label + ".json")).write_text(json.dumps({"result": result, "events": events[chat]}, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
        time.sleep(float(os.environ.get("NEVE_MEDIA_TEST_PAUSE", "0")))
    finally:
        if task_id in api("GET", "/api/tasks").json()["tasks"]:
            api("POST", "/api/tasks/stop/" + task_id)


try:
    assert not api("GET", "/api/tasks").json()["tasks"]
    if not loaded():
        api("POST", "/llamacpp/models/load", json={"filename": "Qwen3.5 9B MTP UDQ4_K_XL.gguf",
            "n_gpu_layers": -1, "n_ctx": 8192, "cache_type": "q8_0", "context_shift": "off",
            "speculative_decoding": "off", "token_prediction": "off"})
    user = api("GET", "/api/v1/auths/").json()
    socket.connect(BASE, socketio_path="ws/socket.io", auth={"token": user["token"]}, transports=["websocket"])
    run("image-complete", {"stable_diffusion": True, "stable_diffusion_quality": "neve_image_2", "stable_diffusion_resolution": "1:1"})
    run("image-stop", {"stable_diffusion": True, "stable_diffusion_quality": "qwen_image_2s", "stable_diffusion_resolution": "1:1"}, cancel=True)
    run("video-complete", {"video_generation": True, "video_generation_model": "minimax_h3", "video_generation_resolution": "480p", "video_generation_duration": "5s"})
    run("video-stop", {"video_generation": True, "video_generation_model": "vdn_h3", "video_generation_resolution": "480p", "video_generation_duration": "5s"}, cancel=True)
finally:
    for chat in created_chats:
        api("DELETE", "/api/v1/chats/" + chat)
    for item in created_files:
        api("DELETE", "/api/v1/files/" + item)
    socket.disconnect()
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
