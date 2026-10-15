"""Bounded recovery helpers shared by local image runtimes."""

import re
import os


def cpu_image_requested(backend: str) -> bool:
    return backend == 'cpu' or (backend == 'cuda12' and os.environ.get('CUDA_VISIBLE_DEVICES') in ('', '-1'))


class ImageGenerationError(RuntimeError):
    def __init__(self, message: str, *, memory_failure: bool = False):
        super().__init__(message)
        self.memory_failure = memory_failure


def cpu_image_size(width: int, height: int, max_side: int = 512) -> tuple[int, int]:
    scale = min(1.0, max_side / max(width, height))
    return tuple(max(32, round(side * scale / 32) * 32) for side in (width, height))


def is_image_memory_error(error: BaseException | str) -> bool:
    if isinstance(error, ImageGenerationError):
        return error.memory_failure
    if isinstance(error, MemoryError):
        return True
    if isinstance(error, OSError) and (error.errno == 12 or getattr(error, 'winerror', None) in (8, 14, 1455)):
        return True
    return bool(re.search(
        r"\bout of (?:device |host )?memory\b|\bOutOfMemoryError\b|\bstd::bad_alloc\b|"
        r"cannot allocate memory|not enough (?:free )?(?:gpu |device |host )?memory|"
        r"ErrorOutOfDeviceMemory|CUDA_ERROR_OUT_OF_MEMORY|CUBLAS_STATUS_ALLOC_FAILED|"
        r"(?:failed to allocate|allocation failed|alloc failed)|paging file is too small|"
        r"cannot make enough memory available",
        str(error), re.IGNORECASE,
    ))


def worker_error(name: str, status: dict) -> RuntimeError:
    # Avoid classifying user prompts echoed in execution inputs as worker errors.
    errors = [item[1] for item in status.get('messages', [])
              if isinstance(item, (tuple, list)) and len(item) > 1
              and item[0] == 'execution_error' and isinstance(item[1], dict)]
    details = '; '.join(str(item.get('exception_type', '')) + ': ' +
                        str(item.get('exception_message', '')) for item in errors)
    memory_failure = any(
        (str(item.get('exception_type', '')).rsplit('.', 1)[-1] not in ('ValueError', 'TypeError', 'FileNotFoundError'))
        and is_image_memory_error(str(item.get('exception_type', '')) + ': ' + str(item.get('exception_message', '')))
        for item in errors
    )
    return ImageGenerationError(f'{name} falhou: {details or status.get("status_str", "erro desconhecido")}',
                                memory_failure=memory_failure)


def monotonic_progress(callback):
    last = 0

    async def report(value):
        nonlocal last
        last = max(last, int(value))
        if callback is not None:
            await callback(last)

    return report
