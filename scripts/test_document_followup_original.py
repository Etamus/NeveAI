"""Read the reported attachment without changing it; write comparison only to logs."""
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.utils.document_edits import inspect_document, apply_document_edits
from neveai.utils.document_edit_planner import propose_document_edits
import pymupdf
from PIL import Image, ImageChops, ImageDraw


def main():
    with sqlite3.connect(f"file:{(ROOT / 'backend/data/neve.db').as_posix()}?mode=ro", uri=True) as connection:
        row = connection.execute("SELECT path FROM file WHERE id = ?", ("a89040f9-dda3-43b5-8872-ce37e22525cd",)).fetchone()
    if not row:
        raise RuntimeError("Reported attachment is not available")
    path = Path(row[0])
    source = path.read_bytes()
    snapshot = inspect_document(source, "pdf")
    complete = AsyncMock(side_effect=AssertionError("This edit must not rewrite the document"))
    edits = asyncio.run(propose_document_edits(snapshot, "Remova o ultimo paragrafo", complete))
    result, report = apply_document_edits(snapshot, edits)
    output = ROOT / "logs/document-followup-original"
    output.mkdir(parents=True, exist_ok=True)
    (output / "edited.pdf").write_bytes(result)
    measurements = []
    with pymupdf.open(stream=source, filetype="pdf") as before, pymupdf.open(stream=result, filetype="pdf") as after:
        assert len(before) == len(after) == 2
        for index in range(len(before)):
            a = before[index].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            b = after[index].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            a.save(output / f"before-{index}.png")
            b.save(output / f"after-{index}.png")
            image_a = Image.frombytes("RGB", (a.width, a.height), a.samples)
            image_b = Image.frombytes("RGB", (b.width, b.height), b.samples)
            for edit in edits:
                if snapshot.references[edit["id"]][0] != index:
                    continue
                for replacement in edit["literal_replacements"]:
                    for rect in before[index].search_for(replacement["old_text"]):
                        box = ((rect.x0-2)*2, (rect.y0-2)*2, (rect.x1+2)*2, (rect.y1+2)*2)
                        ImageDraw.Draw(image_a).rectangle(box, fill="black")
                        ImageDraw.Draw(image_b).rectangle(box, fill="black")
            difference = ImageChops.difference(image_a, image_b).getbbox()
            assert difference is None, (index, difference)
            measurements.append({"page": index+1, "pixel_changes_outside_deletion": 0})
        assert "Inicialmente, Axel" not in after[1].get_text()
        assert "Inicialmente, Axel" in before[1].get_text()
    assert path.read_bytes() == source
    complete.assert_not_awaited()
    summary = {"pages": measurements, "source_sha256": hashlib.sha256(source).hexdigest(),
               "original_unchanged": True, "model_calls": 0, "validation": report}
    (output / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
