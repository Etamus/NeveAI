"""CPU-only comparison on an existing attachment; never writes the active index."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))

import ftfy
import numpy as np
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from neveai.retrieval.attachment_processing import subtitle_documents, embedding_text
from neveai.retrieval.local_embeddings import encode_local
from neveai.retrieval.onnx_embeddings import accelerate_cached_encoder

parser = argparse.ArgumentParser()
parser.add_argument("--file-id", default="3a29aabe-a9e3-4548-8d8e-7e157167b63b")
parser.add_argument("--sample", type=int, default=256)
args = parser.parse_args()
path = next((root / "backend/data/uploads").glob(args.file_id + "_*"))
raw = path.read_bytes()
digest = hashlib.sha256(raw).hexdigest()
text = ftfy.fix_text(raw.decode("utf-8-sig"))
doc = Document(page_content=text, metadata={"name": path.name})
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100, add_start_index=True)
old = splitter.split_documents([doc])
new = splitter.split_documents(subtitle_documents([doc]))
cache = Path.home() / ".cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots"
model_path = next(p for p in cache.iterdir() if (p / "model.safetensors").is_file())
encoder = SentenceTransformer(str(model_path), device="cpu", local_files_only=True)
encoder.encode(["Warm-up"], batch_size=32)

def sample(docs):
    if args.sample == 0:
        return docs
    step = max(1, len(docs) // args.sample)
    return docs[::step][:args.sample]

def measure(values):
    start = time.perf_counter()
    result = encoder.encode(values, batch_size=32)
    return result, round(time.perf_counter() - start, 4)

old_sample, new_sample = sample(old), sample(new)
old_values = [d.page_content.replace("\n", " ") for d in old_sample]
new_values = [embedding_text(d.page_content, d.metadata) for d in new_sample]
_, old_time = measure(old_values)
checked_values = new_values if args.sample else new_values[:256]
reference, new_time = measure(checked_values)
start = time.perf_counter()
bounded = np.asarray(asyncio.run(encode_local(encoder, checked_values, 1)))
bounded_time = time.perf_counter() - start
optimized = accelerate_cached_encoder(encoder, "sentence-transformers/all-MiniLM-L6-v2", model_path)
start = time.perf_counter()
fast = np.asarray(asyncio.run(encode_local(optimized, new_values, 1)))
optimized_time = time.perf_counter() - start

def clipped_count(values):
    lengths = encoder.tokenizer(values, truncation=False, padding=False)["input_ids"]
    return sum(len(item) > encoder.max_seq_length for item in lengths)

print(json.dumps({
    "old_chunks": len(old), "new_chunks": len(new), "sample": len(new_sample),
    "old_sample_seconds": old_time, "new_native_checked_sample_seconds": new_time,
    "bounded_sample_seconds": round(bounded_time, 4),
    "onnx_enabled": optimized is not encoder,
    "encoder_device": str(encoder.device), "encoder_prompts": encoder.prompts,
    "onnx_sample_seconds": round(optimized_time, 4),
    "onnx_vector_max_abs_difference_same_input": float(np.abs(reference - fast[:len(reference)]).max()),
    "checked_vectors": len(reference),
    "vector_max_abs_difference_same_input": float(np.abs(reference - bounded).max()),
    "old_truncated_samples": clipped_count(old_values),
    "new_truncated_samples": clipped_count(new_values),
    "original_unchanged": hashlib.sha256(path.read_bytes()).hexdigest() == digest,
}, indent=2))
