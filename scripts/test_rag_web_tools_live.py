"""Real API/chat tests using only disposable uploads, conversations and outputs."""
import json
import asyncio
import io
from pathlib import Path
import sys
import threading
import time

import pymupdf
import requests
import socketio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
BASE = "http://127.0.0.1:8080"
session = requests.Session()
socket = socketio.Client()
created_chats, created_files, task_ids = [], set(), []
temporary_collections = set()
events, finished, results = {}, {}, []
test_model = None


def api(method, path, **kwargs):
    response = session.request(method, BASE + path, timeout=180, **kwargs)
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


def chat_case(label, messages, features, files=None):
    history = {f"m{i}": {**message, "id": f"m{i}", "parentId": f"m{i-1}" if i else None,
               "childrenIds": [f"m{i+1}"] if i < len(messages)-1 else ["answer"], "done": True}
               for i, message in enumerate(messages)}
    parent = f"m{len(messages)-1}"
    history["answer"] = {"id": "answer", "role": "assistant", "content": "", "parentId": parent,
                         "childrenIds": [], "done": False, "model": model}
    chat = api("POST", "/api/v1/chats/new", json={"chat": {
        "title": "Temporary integration validation: " + label, "models": [model],
        "history": {"currentId": "answer", "messages": history}, "messages": list(history.values()),
        "params": {}, "timestamp": int(time.time() * 1000)}}).json()["id"]
    created_chats.append(chat)
    events[chat], finished[chat] = [], threading.Event()
    start = time.monotonic()
    response = api("POST", "/api/chat/completions", json={
        "model": model, "messages": messages, "stream": True, "features": features, "files": files or [],
        "chat_id": chat, "id": "answer", "parent_id": parent, "parent_message": history[parent],
        "session_id": socket.get_sid(),
        "background_tasks": {"title_generation": False, "tags_generation": False, "follow_up_generation": False},
        "params": {"reasoning_mode": "quick", "no_think": True, "max_tokens": 2048, "function_calling": "default"},
    }).json()
    if response.get("task_id"):
        task_ids.append(response["task_id"])
    assert finished[chat].wait(180), (label, "completion timeout")
    time.sleep(.3)
    answer = api("GET", "/api/v1/chats/" + chat).json()["chat"]["history"]["messages"]["answer"]
    created_files.update(item["id"] for item in answer.get("files", []))
    assert not answer.get("error"), (label, answer.get("error"))
    result = {"case": label, "seconds": round(time.monotonic() - start, 2),
              "file_count": len(answer.get("files", [])), "source_count": len(answer.get("sources", [])),
              "file_names": [item.get("name") or item.get("filename") for item in answer.get("files", [])],
              "statuses": [event["data"].get("action") for event in events[chat] if event.get("type") == "status"]}
    results.append(result)
    print(json.dumps(result), flush=True)
    return answer, result


try:
    assert not api("GET", "/api/tasks").json()["tasks"], "Active user generation"
    user = api("GET", "/api/v1/auths/").json()
    if user.get("token"):
        session.headers["Authorization"] = "Bearer " + user["token"]
    socket.connect(BASE, socketio_path="ws/socket.io", auth={"token": user["token"]}, transports=["websocket"])
    cues = []
    for i in range(1, 181):
        minute, second = divmod(i, 60)
        words = "The group visited a quiet village." if i != 90 else "CHAVE_ESMERALDA opens the northern tower."
        cues.append(f"{i}\n00:{minute:02}:{second:02},000 --> 00:{minute:02}:{second:02},900\n{words}")
    original = "\n\n".join(cues)
    start = time.monotonic()
    file = api("POST", "/api/v1/files/", files={"file": ("temporary-rag-validation.srt", original.encode(), "application/x-subrip")}).json()
    created_files.add(file["id"])
    for _ in range(90):
        file = api("GET", "/api/v1/files/" + file["id"]).json()
        status = file.get("data", {}).get("status")
        if status == "completed":
            break
        assert status != "failed", file.get("data", {}).get("error")
        time.sleep(1)
    assert status == "completed" and file["data"]["content"] == original
    temporary_collections.add("file-" + file["id"])
    for hybrid in (False, True):
        result = api("POST", "/api/v1/retrieval/query/doc", json={"collection_name": "file-" + file["id"],
                     "query": "What opens the northern tower? CHAVE_ESMERALDA", "k": 3,
                     "hybrid": hybrid, "hybrid_bm25_weight": 0, "r": 0}).json()
        assert any("CHAVE_ESMERALDA" in text for group in result["documents"] for text in group)
        assert any("-->" in text for group in result["documents"] for text in group)
    results.append({"case": "rag-upload-and-query", "seconds": round(time.monotonic()-start, 2), "original_preserved": True})

    for label, payload in [
        ("live-web", {"queries": ["Python dataclasses official documentation"], "question": "Pesquise a documentacao oficial de dataclasses do Python"}),
        ("live-web-pdf", {"queries": [], "urls": ["https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"], "question": "Leia o PDF"}),
    ]:
        start = time.monotonic()
        result = api("POST", "/api/v1/retrieval/process/web/search", json=payload).json()
        assert result["status"] and result["pages_read_count"] > 0
        assert result["loaded_count"] <= 4
        results.append({"case": label, "seconds": round(time.monotonic()-start, 2), "pages": result["pages_read_count"]})

    if "--rag-only" in sys.argv:
        raise SystemExit(0)

    loaded = api("GET", "/llamacpp/models/loaded").json()["models"]
    if loaded:
        model = loaded[0]["id"]
    else:
        models = api("GET", "/llamacpp/models").json()["models"]
        candidate = next(item for item in models if "Qwen3.5" in item["filename"] and "9B" in item["filename"])
        loaded_model = api("POST", "/llamacpp/models/load", json={"filename": candidate["filename"], "n_gpu_layers": -1,
                           "n_ctx": 8192, "cache_type": "q8_0", "context_shift": "off", "speculative_decoding": "off", "token_prediction": "off"}).json()
        model = loaded_model.get("id") or candidate["id"]
        test_model = model
    source, _ = chat_case("pdf-create", [{"role": "user", "content": "Crie um PDF sobre batatas com exatamente tres paragrafos curtos, sem listas."}], {"file_generation": True})
    assert len(source.get("files", [])) == 1
    attached = source["files"][0]
    original_pdf = api("GET", "/api/v1/files/" + attached["id"] + "/content").content
    assert original_pdf.startswith(b"%PDF-")
    revised, _ = chat_case("pdf-remove-paragraph", [{"role": "user", "content": "Remova o ultimo paragrafo", "files": [attached]}], {"file_generation": True}, [attached])
    assert len(revised.get("files", [])) == 1
    revised_pdf = api("GET", "/api/v1/files/" + revised["files"][0]["id"] + "/content").content
    with pymupdf.open(stream=original_pdf, filetype="pdf") as before, pymupdf.open(stream=revised_pdf, filetype="pdf") as after:
        assert len(before) == len(after)
        assert 0 < len("".join(page.get_text() for page in after).strip()) < len("".join(page.get_text() for page in before).strip())
    thanks, info = chat_case("thanks-no-document", [{"role": "assistant", "content": "Arquivo preparado.", "files": [attached]}, {"role": "user", "content": "Obrigado!"}], {"file_generation": True}, [attached])
    assert not thanks.get("files") and "file_generation" not in info["statuses"]
    web_answer, info = chat_case("web-chat", [{"role": "user", "content": "Pesquise a documentacao oficial de dataclasses do Python e cite a fonte."}], {"web_search": True})
    assert "web_search" in info["statuses"] and web_answer.get("sources")
    combined, info = chat_case("web-document", [{"role": "user", "content": "Crie um PDF curto explicando dataclasses do Python, com referencias oficiais pesquisadas na web."}], {"web_search": True, "file_generation": True})
    assert combined.get("files") and "web_search" in info["statuses"]
    assert api("GET", "/api/v1/files/" + combined["files"][0]["id"] + "/content").content.startswith(b"%PDF-")
    if "--web-tools-repeat" in sys.argv:
        for label, prompt in [
            ("web-document-repeat", "Crie um PDF curto explicando dataclasses do Python, com referencias oficiais pesquisadas na web."),
            ("web-document-got", "Crie um PDF curto: qual a melhor temporada de GOT? Inclua fontes pesquisadas na web."),
            ("web-document-docx", "Crie um DOCX curto sobre a diferenca entre list e tuple em Python, com fontes oficiais pesquisadas na web."),
        ]:
            repeated, info = chat_case(label, [{"role": "user", "content": prompt}], {"web_search": True, "file_generation": True})
            assert repeated.get("files") and "web_search" in info["statuses"]
            data = api("GET", "/api/v1/files/" + repeated["files"][0]["id"] + "/content").content
            if label.endswith("docx"):
                import zipfile
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    assert "word/document.xml" in archive.namelist()
            else:
                assert data.startswith(b"%PDF-")
    from docx import Document
    from neveai.utils.document_edits import inspect_document, apply_document_edits
    from neveai.utils.document_edit_planner import propose_document_edits
    text = "Original content stays unchanged. " * 400 + "Current approval status: pending."
    document = Document(); document.add_paragraph(text)
    stream = io.BytesIO(); document.save(stream)
    snapshot = inspect_document(stream.getvalue(), "docx")
    proposal_calls = []
    async def complete(messages, schema):
        proposal_calls.append(True)
        response = api("POST", "/api/chat/completions", json={
            "model": model, "messages": messages, "stream": False, "temperature": 0, "max_tokens": 4096,
            "params": {"reasoning_mode": "quick", "no_think": True, "max_tokens": 4096},
            "response_format": {"type": "json_schema", "json_schema": {"name": "native_document_edit", "strict": True, "schema": schema}},
        }).json()
        return json.loads(response["choices"][0]["message"]["content"])
    start = time.monotonic()
    changes = asyncio.run(propose_document_edits(snapshot, "Set the final approval status to approved. Keep the rest exactly unchanged.", complete))
    edited = inspect_document(apply_document_edits(snapshot, changes)[0], "docx")
    assert proposal_calls and edited.elements[0]["text"] == text.replace("status: pending", "status: approved")
    results.append({"case": "large-native-docx-real-planner", "calls": len(proposal_calls), "seconds": round(time.monotonic()-start, 2), "unaffected_text_preserved": True})
finally:
    for task in task_ids:
        session.post(BASE + "/api/tasks/stop/" + task, timeout=15)
    for chat in created_chats:
        api("DELETE", "/api/v1/chats/" + chat)
    for file_id in created_files:
        api("DELETE", "/api/v1/files/" + file_id)
    if test_model:
        api("POST", "/llamacpp/models/unload", json={"model_id": test_model})
    if socket.connected:
        socket.disconnect()
    if temporary_collections:
        import chromadb
        from chromadb.config import Settings
        vector_path = (ROOT / "backend/data/vector_db").resolve()
        assert vector_path.is_relative_to(ROOT.resolve())
        client = chromadb.PersistentClient(path=str(vector_path), settings=Settings(allow_reset=True, anonymized_telemetry=False))
        for collection in temporary_collections:
            assert collection in {"file-" + identifier for identifier in created_files}
            client.delete_collection(collection)
    output = "rag-web-tools-rag-smoke.json" if "--rag-only" in sys.argv else "rag-web-tools-live.json"
    (ROOT / "logs" / output).write_text(json.dumps(results, indent=2), encoding="utf-8")
