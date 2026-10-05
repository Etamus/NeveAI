"""Recover PDF text whose positioned words were extracted as separate lines."""

from functools import lru_cache
from pathlib import Path


def has_fragmented_pdf_text(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return len(lines) >= 40 and sum(len(line.split()) == 1 for line in lines) / len(lines) > 0.85


@lru_cache(maxsize=16)
def read_pdf_layout(path: str, modified: int, size: int) -> str:
    from pypdf import PdfReader

    if size > 20 * 1024 * 1024:
        return ""
    reader = PdfReader(path)
    if len(reader.pages) > 200:
        return ""
    return "\n\n".join(page.extract_text(extraction_mode="layout").strip() for page in reader.pages)


def repair_pdf_content(path: str, text: str) -> str:
    if not has_fragmented_pdf_text(text):
        return text
    try:
        stat = Path(path).stat()
        return read_pdf_layout(path, stat.st_mtime_ns, stat.st_size) or text
    except Exception:
        return text
