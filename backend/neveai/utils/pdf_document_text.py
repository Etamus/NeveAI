"""Tools-only PDF extraction, with lazy CPU OCR for image-only pages."""

from functools import lru_cache
from pathlib import Path
from threading import RLock

from neveai.utils.generated_files import GeneratedFileError

PDF_RENDER_LOCK = RLock()


@lru_cache(maxsize=4)
def _read_pdf(path: str, modified: int, size: int) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(path)
    if reader.is_encrypted:
        raise GeneratedFileError("O PDF esta protegido por senha.")
    if len(reader.pages) > 200 or size > 32 * 1024 * 1024:
        raise GeneratedFileError(
            "Ferramentas aceita PDFs de ate 200 paginas e 32 MB por arquivo."
        )
    pages, missing = [], []
    for index, page in enumerate(reader.pages):
        text = page.extract_text(extraction_mode="layout").strip()
        pages.append({"number": index + 1, "text": text})
        if not text and page.images:
            missing.append(index)
    if len(missing) > 30:
        raise GeneratedFileError(
            "O PDF precisa de OCR em mais de 30 paginas; divida-o para processamento seguro."
        )
    if missing:
        import numpy as np
        import pypdfium2 as pdfium
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR(
            intra_op_num_threads=2,
            inter_op_num_threads=1,
            det_use_cuda=False,
            cls_use_cuda=False,
            rec_use_cuda=False,
            det_use_dml=False,
            cls_use_dml=False,
            rec_use_dml=False,
        )
        with PDF_RENDER_LOCK:
            document = pdfium.PdfDocument(path)
            try:
                for index in missing:
                    page = document[index]
                    bitmap = None
                    try:
                        width, height = page.get_size()
                        scale = min(2, 2000 / max(width, height))
                        bitmap = page.render(scale=scale)
                        result, _ = engine(np.array(bitmap.to_pil().convert("RGB")))
                        if not result:
                            raise GeneratedFileError(
                                f"Nao foi possivel ler a pagina digitalizada {index + 1}; envie uma copia mais nitida."
                            )
                        pages[index]["text"] = "\n".join(
                            str(item[1]) for item in result
                        )
                        pages[index]["ocr"] = True
                        pages[index]["ocr_confidence"] = min(
                            float(item[2]) for item in result
                        )
                        if pages[index]["ocr_confidence"] < 0.6:
                            raise GeneratedFileError(
                                f"OCR com baixa confianca na pagina {index + 1}; revise a digitalizacao antes de editar."
                            )
                    finally:
                        if bitmap:
                            bitmap.close()
                        page.close()
            finally:
                document.close()
    if sum(len(page["text"]) for page in pages) > 4_000_000:
        raise GeneratedFileError("O texto do PDF excede 4 milhoes de caracteres.")
    return {
        "format": "pdf",
        "pages": pages,
        "ocr_pages": [index + 1 for index in missing],
    }


def read_pdf_document(path: str) -> dict:
    source = Path(path)
    stat = source.stat()
    return _read_pdf(str(source.resolve()), stat.st_mtime_ns, stat.st_size)
