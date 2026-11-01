"""Bounded, content-addressed BM25 indexes; request metadata is never shared."""

import hashlib
import threading
from collections import OrderedDict

_indexes = OrderedDict()
_lock = threading.Lock()
_MAX_BYTES = 2 * 1024 * 1024
_MAX_ENTRIES = 4


def create_bm25_retriever(collection, texts, metadatas, k):
    from langchain_community.retrievers import BM25Retriever
    from langchain_core.documents import Document

    digest = hashlib.sha256()
    size = 0
    for text in texts:
        raw = text.encode("utf-8")
        size += len(raw)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    key = (collection, digest.digest())
    # Index construction and access happen in a worker, not in the event loop.
    with _lock:
        saved = _indexes.pop(key, None)
        if saved is None:
            retriever = BM25Retriever.from_texts(texts=texts, metadatas=metadatas, k=k)
            saved = (retriever.vectorizer, size)
        if size <= _MAX_BYTES:
            _indexes[key] = saved
            while len(_indexes) > _MAX_ENTRIES or sum(item[1] for item in _indexes.values()) > _MAX_BYTES:
                _indexes.popitem(last=False)
    # Reranking adds scores to metadata. Each request must own its documents.
    return BM25Retriever(
        vectorizer=saved[0], k=k,
        docs=[Document(page_content=text, metadata=dict(meta)) for text, meta in zip(texts, metadatas)],
    )
