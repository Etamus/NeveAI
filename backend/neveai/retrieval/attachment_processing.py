"""Bounded attachment preprocessing; originals and non-subtitle documents stay intact."""
import os
import re

from langchain_core.documents import Document

_CUE = re.compile(
    r"(?m)^(?:(?:\A|(?<=\n\n))\d+[ \t]*\n)?(?P<start>\d{2,}:\d{2}:\d{2}[,.]\d{3})"
    r"[ \t]+-->[ \t]+(?P<end>\d{2,}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n"
)
_TIMECODE = re.compile(r"(?m)^(?P<start>\d{2,}:\d{2}:\d{2}[,.]\d{3})[ \t]+-->[ \t]+(?P<end>\d{2,}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n")


def subtitle_documents(docs, chunk_size=1000, chunk_overlap=100):
    """Compact only well-formed SRT, retaining cue provenance and every dialogue line."""
    if os.environ.get("NEVE_RAG_SUBTITLE_INDEXING", "true").lower() in {"0", "false", "off", "no"}:
        return docs
    result = []
    for doc in docs:
        if doc.metadata.get("subtitle_text"):
            result.append(doc)
            continue
        name = str(doc.metadata.get("name") or doc.metadata.get("source") or "")
        if not name.lower().endswith(".srt"):
            result.append(doc)
            continue
        text = doc.page_content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
        cues = list(_CUE.finditer(text))
        if cues and not text[:cues[0].end()].strip().splitlines()[0].isdigit():
            # Unnumbered transcripts must keep numeric dialogue, even after blank lines.
            cues = list(_TIMECODE.finditer(text))
        if not cues or text[:cues[0].start()].strip("\ufeff \n\t"):
            result.append(doc)
            continue
        sections, current, size, first, last = [], [], 0, None, None
        last_start = None

        def flush():
            nonlocal current, size, first
            if current:
                sections.append(Document(page_content="\n".join(current), metadata={
                    **doc.metadata, "subtitle_start": first, "subtitle_end": last,
                    "subtitle_text": True,
                }))
            current, size, first = [], 0, None

        for index, cue in enumerate(cues):
            end = cues[index + 1].start() if index + 1 < len(cues) else len(text)
            dialogue = text[cue.end():end].strip()
            content = f"{cue['start']} --> {cue['end']}\n{dialogue}"
            # Reset timestamps can mark a new concatenated session; do not merge across it.
            if current and (size + len(content) + 1 > chunk_size or cue["start"] < last_start):
                reset = cue["start"] < last_start
                overlap = current[-1] if chunk_overlap > 0 and not reset and len(current[-1]) <= min(chunk_overlap, chunk_size // 3) else ""
                flush()
                if overlap:
                    current, size, first = [overlap], len(overlap) + 1, last_start
            if dialogue:
                first = first or cue["start"]
                last = cue["end"]
                last_start = cue["start"]
                current.append(content)
                size += len(content) + 1
        flush()
        result.extend(sections or [doc])
    return result


def embedding_text(text, metadata):
    # Only the vector input omits technical timecodes; retrieved text retains them.
    if metadata.get("subtitle_text"):
        text = _TIMECODE.sub("", text)
    return text.replace("\n", " ")
