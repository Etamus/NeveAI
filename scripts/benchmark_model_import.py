"""Measure the actual importer with network-sized chunks and temporary files."""
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from neveai.utils.local_model_files import import_model_stream


async def run():
    samples = []
    size = 128 * 1024 * 1024
    block = bytes(65536)
    with tempfile.TemporaryDirectory(prefix='neve-import-bench-') as temporary:
        for iteration in range(3):
            async def stream():
                yield b'GGUF' + (3).to_bytes(4, 'little') + block[8:]
                for _ in range(size // len(block) - 1):
                    yield block
            started = time.perf_counter()
            result = await import_model_stream(Path(temporary), f'Model{iteration}.gguf', stream())
            samples.append({'bytes': result['file_size'], 'seconds': time.perf_counter() - started})
    print(json.dumps(samples))


asyncio.run(run())
