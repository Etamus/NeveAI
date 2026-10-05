import logging
import ftfy
import sys

from pathlib import Path as _Path

from langchain_community.document_loaders import (BSHTMLLoader, Docx2txtLoader, OutlookMessageLoader, PyPDFLoader, TextLoader, UnstructuredEPubLoader, UnstructuredODTLoader, UnstructuredPowerPointLoader, UnstructuredRSTLoader, UnstructuredXMLLoader)
from langchain_core.documents import Document


class FastSpreadsheetLoader:
    """Fast loader for XLSX, XLS and CSV files using pandas.

    Replaces the slow UnstructuredExcelLoader / CSVLoader for large files.
    Produces compact tabular Documents: one header line followed by CSV-style
    value rows (no repeated column names), so the normal text-splitter can
    handle them.  Each document is ~100 rows which keeps chunk count low and
    preserves full row context for RAG retrieval.
    """

    ROWS_PER_CHUNK = 100

    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> list[Document]:
        import pandas as pd

        file_ext = _Path(self.file_path).suffix.lower()

        # ---- read into {sheet_name: DataFrame} ----------------------------
        if file_ext == ".csv":
            df = None
            for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
                try:
                    df = pd.read_csv(self.file_path, encoding=enc, dtype=str)
                    break
                except UnicodeDecodeError:
                    continue
            if df is None:
                df = pd.read_csv(self.file_path, encoding="latin-1", dtype=str)
            dfs = {"Sheet1": df}
        else:
            engine = "openpyxl" if file_ext == ".xlsx" else "xlrd"
            xl = pd.ExcelFile(self.file_path, engine=engine)
            dfs = {sheet: xl.parse(sheet, dtype=str) for sheet in xl.sheet_names}

        # ---- convert to Documents ----------------------------------------
        docs: list[Document] = []
        for sheet_name, df in dfs.items():
            if df.empty:
                continue
            df = df.fillna("")
            headers = [str(c) for c in df.columns]
            header_line = "Columns: " + " | ".join(headers)
            total = len(df)

            for start in range(0, total, self.ROWS_PER_CHUNK):
                batch = df.iloc[start : start + self.ROWS_PER_CHUNK]
                lines: list[str] = [header_line]

                # itertuples is ~10x faster than iterrows for large DataFrames
                for row in batch.itertuples(index=False, name=None):
                    vals = " | ".join(str(v) for v in row)
                    if vals.replace("|", "").strip():
                        lines.append(vals)

                if len(lines) > 1:  # more than just the header
                    docs.append(
                        Document(
                            page_content="\n".join(lines),
                            metadata={
                                "source": self.file_path,
                                "sheet": sheet_name,
                                "rows": f"{start + 1}-{min(start + self.ROWS_PER_CHUNK, total)}",
                            },
                        )
                    )

        return docs

from neveai.env import GLOBAL_LOG_LEVEL

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)

known_source_ext = [
    "go",
    "py",
    "java",
    "sh",
    "bat",
    "ps1",
    "cmd",
    "js",
    "ts",
    "css",
    "cpp",
    "hpp",
    "h",
    "c",
    "cs",
    "sql",
    "log",
    "ini",
    "pl",
    "pm",
    "r",
    "dart",
    "dockerfile",
    "env",
    "php",
    "hs",
    "hsc",
    "lua",
    "nginxconf",
    "conf",
    "m",
    "mm",
    "plsql",
    "perl",
    "rb",
    "rs",
    "db2",
    "scala",
    "bash",
    "swift",
    "vue",
    "svelte",
    "ex",
    "exs",
    "erl",
    "tsx",
    "jsx",
    "hs",
    "lhs",
    "json",
    "yaml",
    "yml",
    "toml",
]


class Loader:
    def __init__(self, engine: str = "", **kwargs):
        self.engine = engine
        self.user = kwargs.get("user", None)
        self.kwargs = kwargs

    def load(
        self, filename: str, file_content_type: str, file_path: str
    ) -> list[Document]:
        loader = self._get_loader(filename, file_content_type, file_path)
        docs = loader.load()

        if filename.lower().endswith('.pdf'):
            from neveai.retrieval.pdf_layout import has_fragmented_pdf_text
            if any(has_fragmented_pdf_text(doc.page_content) for doc in docs):
                # Preserve positioned lines and paragraphs rather than one word per line.
                try:
                    from pypdf import PdfReader
                    pages = PdfReader(file_path).pages
                    if len(docs) == len(pages):
                        for doc, page in zip(docs, pages):
                            if has_fragmented_pdf_text(doc.page_content):
                                doc.page_content = page.extract_text(extraction_mode='layout') or doc.page_content
                    elif len(docs) == 1:
                        doc = docs[0]
                        doc.page_content = '\n\n'.join(page.extract_text(extraction_mode='layout') for page in pages) or doc.page_content
                except Exception:
                    logging.getLogger(__name__).debug('PDF layout fallback', exc_info=True)

        return [
            Document(
                page_content=ftfy.fix_text(doc.page_content), metadata=doc.metadata
            )
            for doc in docs
        ]

    def _is_text_file(self, file_ext: str, file_content_type: str) -> bool:
        return file_ext in known_source_ext or (
            file_content_type
            and file_content_type.find("text/") >= 0
            # Avoid text/html files being detected as text
            and not file_content_type.find("html") >= 0
        )

    def _get_loader(self, filename: str, file_content_type: str, file_path: str):
        file_ext = filename.split(".")[-1].lower()

        if file_ext == "pdf":
            return PyPDFLoader(
                file_path,
                extract_images=self.kwargs.get("PDF_EXTRACT_IMAGES"),
                mode=self.kwargs.get("PDF_LOADER_MODE", "page"),
            )
        if file_ext == "csv":
            return FastSpreadsheetLoader(file_path)
        if file_ext == "rst":
            return UnstructuredRSTLoader(file_path, mode="elements")
        if file_ext == "xml":
            return UnstructuredXMLLoader(file_path)
        if file_ext in {"htm", "html"}:
            return BSHTMLLoader(file_path, open_encoding="unicode_escape")
        if file_ext == "md":
            return TextLoader(file_path, autodetect_encoding=True)
        if file_content_type == "application/epub+zip":
            return UnstructuredEPubLoader(file_path)
        if (
            file_content_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or file_ext == "docx"
        ):
            return Docx2txtLoader(file_path)
        if file_content_type in {
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        } or file_ext in {"xls", "xlsx"}:
            return FastSpreadsheetLoader(file_path)
        if file_content_type in {
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        } or file_ext in {"ppt", "pptx"}:
            return UnstructuredPowerPointLoader(file_path)
        if file_ext == "msg":
            return OutlookMessageLoader(file_path)
        if file_ext == "odt":
            return UnstructuredODTLoader(file_path)
        return TextLoader(file_path, autodetect_encoding=True)
