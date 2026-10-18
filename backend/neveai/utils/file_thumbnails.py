import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading
from weakref import WeakValueDictionary

from PIL import Image, ImageOps


THUMBNAIL_SIZE = (640, 480)
_generation_slots = threading.BoundedSemaphore(2)
_cache_locks = WeakValueDictionary()
_cache_lock_guard = threading.Lock()


def get_image_thumbnail(source: Path, cache_dir: Path) -> Path:
    stat = source.stat()
    fingerprint = json.dumps(
        [str(source.resolve()), stat.st_mtime_ns, stat.st_size, THUMBNAIL_SIZE, 1]
    ).encode()
    target = cache_dir / f"{hashlib.sha256(fingerprint).hexdigest()}.webp"
    if target.is_file():
        return target

    # Limit simultaneous full-resolution decodes on a cold library load.
    with _cache_lock_guard:
        lock = _cache_locks.setdefault(target, threading.Lock())
    with lock, _generation_slots:
        if target.is_file():
            return target
        cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with Image.open(source) as original:
                draft_size = (
                    THUMBNAIL_SIZE[::-1]
                    if original.getexif().get(274) in (5, 6, 7, 8)
                    else THUMBNAIL_SIZE
                )
                original.draft("RGB", draft_size)
                ImageOps.exif_transpose(original, in_place=True)
                image = original
                mode = (
                    "RGBA"
                    if "A" in image.getbands() or "transparency" in image.info
                    else "RGB"
                )
                if image.mode != mode:
                    image = image.convert(mode)
                scale = min(
                    1, image.width / THUMBNAIL_SIZE[0], image.height / THUMBNAIL_SIZE[1]
                )
                size = tuple(max(1, round(edge * scale)) for edge in THUMBNAIL_SIZE)
                cover_scale = max(size[0] / image.width, size[1] / image.height)
                image.thumbnail(
                    (
                        math.ceil(image.width * cover_scale),
                        math.ceil(image.height * cover_scale),
                    ),
                    Image.Resampling.LANCZOS,
                    reducing_gap=2.0,
                )
                preview = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
                with tempfile.NamedTemporaryFile(
                    dir=cache_dir, suffix=".tmp", delete=False
                ) as output:
                    temporary = Path(output.name)
                    preview.save(
                        output,
                        format="WEBP",
                        quality=82,
                        method=1,
                        icc_profile=image.info.get("icc_profile", b""),
                    )
            os.replace(temporary, target)
            return target
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
