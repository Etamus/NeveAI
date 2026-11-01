"""Optional CPU acceleration using cached FP32 weights and native pooling modules."""
import logging
import os
import statistics
import time
from pathlib import Path

import numpy as np
import psutil

log = logging.getLogger(__name__)


class CachedOnnxEncoder:
    def __init__(self, original, session):
        self.original = original
        self.session = session

    def __getattr__(self, name):
        return getattr(self.original, name)

    def encode(self, sentences, batch_size=32, prompt=None):
        if self.session is None:
            return self.original.encode(sentences, batch_size=batch_size,
                                        **({"prompt": prompt} if prompt else {}))
        try:
            import torch

            scalar = isinstance(sentences, str)
            values = [sentences] if scalar else sentences
            vectors = []
            for start in range(0, len(values), batch_size):
                batch = values[start:start + batch_size]
                features = self.original.tokenize([prompt + text for text in batch] if prompt else batch)
                inputs = {item.name: features[item.name].numpy() for item in self.session.get_inputs()}
                tokens = self.session.run(None, inputs)[0]
                features["token_embeddings"] = torch.from_numpy(tokens)
                # Keep Sentence Transformers' own pooling and normalization behavior.
                with torch.inference_mode():
                    for module in list(self.original._modules.values())[1:]:
                        features = module(features)
                vectors.append(features["sentence_embedding"].numpy())
            result = np.concatenate(vectors) if vectors else np.empty((0, 384), dtype=np.float32)
            return result[0] if scalar else result
        except Exception:
            self.session = None
            log.warning("Cached ONNX encoder failed; returning to the original CPU encoder", exc_info=True)
            return self.original.encode(sentences, batch_size=batch_size,
                                        **({"prompt": prompt} if prompt else {}))


def accelerate_cached_encoder(encoder, model_name, model_path):
    """Never download, export or select quantized weights automatically."""
    if os.environ.get("NEVE_RAG_CPU_ONNX", "true").lower() in {"0", "false", "off", "no"}:
        return encoder
    if model_name != "sentence-transformers/all-MiniLM-L6-v2":
        return encoder
    try:
        if str(encoder.device) != "cpu" or any(encoder.prompts.values()) or encoder.default_prompt_name:
            return encoder
        if psutil.virtual_memory().available < 4 * 1024**3:
            return encoder
        weights = Path(model_path) / "onnx/model_O2.onnx"
        if not weights.is_file() or weights.stat().st_size < 1024:
            return encoder
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = min(8, psutil.cpu_count(logical=False) or 2)
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(weights), sess_options=options,
                                       providers=["CPUExecutionProvider"])
        optimized = CachedOnnxEncoder(encoder, session)
        probes = ["A short retrieval query.", "Informacoes sobre a ultima sessao, personagens e acontecimentos.",
                  "00:01:02,000 --> 00:01:05,000\nText with numbers 123 and punctuation!"]
        expected = encoder.encode(probes, batch_size=3)
        actual = optimized.encode(probes, batch_size=3)
        if optimized.session is None or not np.allclose(expected, actual, rtol=1e-4, atol=1e-5):
            log.warning("Cached ONNX vector check failed; preserving the original encoder")
            return encoder
        samples = [(probes[index % len(probes)] + " ") * 12 for index in range(32)]
        original_times, optimized_times = [], []
        for _ in range(2):
            start = time.perf_counter()
            encoder.encode(samples, batch_size=32)
            original_times.append(time.perf_counter() - start)
            start = time.perf_counter()
            optimized.encode(samples, batch_size=32)
            optimized_times.append(time.perf_counter() - start)
        if optimized.session is not None and statistics.median(optimized_times) < statistics.median(original_times) * .9:
            log.info("Using validated faster cached FP32 ONNX embeddings on CPU")
            return optimized
        log.info("Cached ONNX did not improve CPU throughput sufficiently; preserving PyTorch")
    except Exception:
        log.warning("CPU ONNX acceleration unavailable; preserving PyTorch", exc_info=True)
    return encoder
