"""Resolve the initial progress canvas without loading generation models."""
import io
import os
from typing import Optional

from PIL import Image


def initial_image_dimensions(quality: str, resolution: str, references: list[str],
                             user_id: Optional[str], default: tuple[int, int]) -> tuple[int, int]:
    from neveai.routers import stable_diffusion as sd
    from neveai.utils.image_memory import cpu_image_requested, cpu_image_size

    if quality == "minimax_h3_image":
        from neveai.routers.image_h3_generation import canvas_size
        size = None
        if references:
            raw = sd._read_image_reference_bytes(references[0], user_id)
            with Image.open(io.BytesIO(raw)) as image:
                size = image.size[::-1] if image.getexif().get(274) in (5, 6, 7, 8) else image.size
        return canvas_size(resolution, size)
    if not references or quality not in {sd.QWEN_IMAGE_21_OFFICIAL_QUALITY, "qwen_image_2s"}:
        return default
    backend = sd._preferred_sd_cpp_windows_backend() if os.name == "nt" else None
    if quality == "qwen_image_2s" and backend == "vulkan":
        return sd.qwen_image_dimensions(resolution)

    raw = sd._read_image_reference_bytes(references[0], user_id)
    with Image.open(io.BytesIO(raw)) as image:
        size = image.size[::-1] if image.getexif().get(274) in (5, 6, 7, 8) else image.size
    cpu = cpu_image_requested(backend) if backend else False
    if quality == sd.QWEN_IMAGE_21_OFFICIAL_QUALITY:
        from neveai.routers import image_quality_generation as generation
        runtime = generation.NeveImage21Runtime()
        runtime._cpu_mode = runtime._memory_saver = cpu
        model = generation.EDIT_MODEL_FILE if not cpu and generation._prefer_int8_edit(len(references)) else generation.MODEL_FILE
        return runtime._reference_size(*size, model, 0, len(references),
                                       optimized_edit=runtime._optimized_edit_available(model))
    if quality == "qwen_image_2s":
        from neveai.routers.image_fast_generation import _reference_size
        size = _reference_size(*size, 0, len(references))
        return cpu_image_size(*size, max_side=512) if cpu else size
    return default
