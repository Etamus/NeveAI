"""Read-only diagnostics for the attachment discussed in the RAG audit."""
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import ftfy
import psutil
from langchain_text_splitters import RecursiveCharacterTextSplitter

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from langchain_core.documents import Document
from neveai.retrieval.attachment_processing import subtitle_documents
file_id = "3a29aabe-a9e3-4548-8d8e-7e157167b63b"
path = next((root / "backend/data/uploads").glob(file_id + "_*"))
raw = path.read_bytes()
digest = hashlib.sha256(raw).hexdigest()
start = time.perf_counter()
text = ftfy.fix_text(raw.decode("utf-8-sig"))
decode_ms = (time.perf_counter() - start) * 1000
start = time.perf_counter()
chunks = RecursiveCharacterTextSplitter(
    chunk_size=1000, chunk_overlap=100, add_start_index=True
).split_text(text)
result = {
    "bytes": len(raw), "characters": len(text), "lines": len(text.splitlines()),
    "decode_fix_ms": round(decode_ms, 2), "chunks": len(chunks),
    "split_ms": round((time.perf_counter() - start) * 1000, 2),
    "timestamp_lines": sum(bool(re.match(r"^\d\d:\d\d:\d\d[,\.]\d+\s+-->", line)) for line in text.splitlines()),
}
result["structured_chunks"] = len(RecursiveCharacterTextSplitter(
    chunk_size=1000, chunk_overlap=100, add_start_index=True
).split_documents(subtitle_documents([Document(page_content=text, metadata={"name": path.name})])))
db = root / "backend/data/vector_db/chroma.sqlite3"
with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as con:
    collection = con.execute("SELECT id FROM collections WHERE name = ?", ("file-" + file_id,)).fetchone()
    if collection:
        result["indexed_chunks"] = con.execute(
            "SELECT count(*) FROM embeddings WHERE segment_id IN (SELECT id FROM segments WHERE collection = ?)",
            (collection[0],),
        ).fetchone()[0]
for connection in psutil.net_connections(kind="tcp"):
    if connection.laddr.port == 8080 and connection.status == psutil.CONN_LISTEN:
        env = psutil.Process(connection.pid).environ()
        result["backend_environment"] = {key: env.get(key, "<unset>") for key in (
            "USE_CUDA_DOCKER", "SENTENCE_TRANSFORMERS_BACKEND", "DEVICE_TYPE"
        )}
        break
result["original_unchanged"] = hashlib.sha256(path.read_bytes()).hexdigest() == digest
print(json.dumps(result, indent=2))
