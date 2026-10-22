"""Small CPU-only click selector with a bounded, short-lived embedding cache."""

import base64
from collections import OrderedDict
import hashlib
import io
import threading
import time

from PIL import Image, ImageOps

from neveai.routers.image_fast_generation import MODELS_DIR, _sha256

REVISION = "0d3b403339b4674a82493d5e97964dd78089ddc8"
ASSETS = {
    "mobile_sam_image_encoder.onnx": (28157093, "580f5fb648ea1062c0aabc26217aed56921985f03f0cbbd852bba81d760cc749"),
    "sam_mask_decoder_single.onnx": (16501323, "93915fc7c993ab9d59ab8c9ccd3bce37f7509c81ab4150a74abd4d2abbd8570d"),
}


class ClickSelector:
    def __init__(self):
        self.lock = threading.Lock()
        self.encoder = self.decoder = None
        self.embeddings = OrderedDict()

    def _load(self):
        if self.encoder is not None:
            return
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        directory = MODELS_DIR / "neve_modes" / "segmentation"
        paths = []
        for name, (size, digest) in ASSETS.items():
            path = directory / name
            if not path.is_file() or path.stat().st_size != size:
                hf_hub_download("Acly/MobileSAM", name, revision=REVISION, local_dir=str(directory))
            if _sha256(path) != digest:
                raise RuntimeError("Arquivo do seletor de objetos invalido: " + name)
            paths.append(str(path))
        config = ort.SessionOptions()
        config.intra_op_num_threads = 2
        config.inter_op_num_threads = 1
        config.enable_cpu_mem_arena = False
        encoder = ort.InferenceSession(paths[0], sess_options=config, providers=["CPUExecutionProvider"])
        decoder = ort.InferenceSession(paths[1], sess_options=config, providers=["CPUExecutionProvider"])
        self.encoder, self.decoder = encoder, decoder

    def select(self, raw, positive, negative, user_id, *, prepare=False):
        import numpy as np
        with self.lock:
            self._load()
            now = time.monotonic()
            for key in list(self.embeddings):
                if now - self.embeddings[key][0] > 120:
                    del self.embeddings[key]
            key = (user_id, hashlib.sha256(raw).digest())
            cached = self.embeddings.pop(key, None)
            if cached is None:
                with Image.open(io.BytesIO(raw)) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                if image.width * image.height > 33_554_432:
                    raise ValueError("A imagem excede o limite de selecao.")
                scale = 1024 / max(image.size)
                size = tuple(max(1, int(side * scale + 0.5)) for side in image.size)
                pixels = np.asarray(image.resize(size, Image.Resampling.BILINEAR), dtype=np.float32)
                embedding = self.encoder.run(None, {"input_image": pixels})[0]
                cached = (now, embedding, image.size, size)
            self.embeddings[key] = (now, *cached[1:])
            while len(self.embeddings) > 2:
                self.embeddings.popitem(last=False)
            if prepare:
                return None
            _, embedding, (width, height), (scaled_width, scaled_height) = cached
            coords = [[p.x * scaled_width, p.y * scaled_height] for p in [*positive, *negative]] + [[0, 0]]
            labels = [1] * len(positive) + [0] * len(negative) + [-1]
            output = self.decoder.run(None, {
                "image_embeddings": embedding,
                "point_coords": np.asarray([coords], dtype=np.float32),
                "point_labels": np.asarray([labels], dtype=np.float32),
                "mask_input": np.zeros((1, 1, 256, 256), dtype=np.float32),
                "has_mask_input": np.zeros(1, dtype=np.float32),
                "orig_im_size": np.asarray([height, width], dtype=np.float32),
            })[0]
            mask = Image.fromarray((output[0, 0] > 0).astype("uint8") * 255)
            mask.thumbnail((1536, 1536), Image.Resampling.NEAREST)
            data = io.BytesIO()
            mask.save(data, format="PNG")
            return "data:image/png;base64," + base64.b64encode(data.getvalue()).decode("ascii")


click_selector = ClickSelector()
