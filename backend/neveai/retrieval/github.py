import hashlib
import io
import json
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

import requests
from langchain_core.documents import Document

from neveai.config import CACHE_DIR

GITHUB_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?github\.com/[^\s<>\"']+", re.IGNORECASE
)
REPOSITORY_PART_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")

MAX_REPOSITORIES_PER_MESSAGE = 3
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_INDEXED_BYTES = 25 * 1024 * 1024
MAX_FILE_BYTES = 1_500_000
MAX_FILES = 4_000
MAX_CHUNK_LINES = 120
MAX_CHUNK_CHARS = 6_000
CHUNK_OVERLAP_LINES = 15
CACHE_TTL_SECONDS = 30 * 60

IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".svelte-kit",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
    "venv",
}
IGNORED_FILENAMES = {
    "bun.lockb",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}
TEXT_EXTENSIONS = {
    ".astro",
    ".bat",
    ".c",
    ".cc",
    ".cfg",
    ".clj",
    ".cmake",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".cxx",
    ".dart",
    ".env",
    ".ex",
    ".exs",
    ".fish",
    ".fs",
    ".fsx",
    ".go",
    ".graphql",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".ipynb",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".less",
    ".lua",
    ".md",
    ".mdx",
    ".mjs",
    ".mm",
    ".php",
    ".pl",
    ".properties",
    ".ps1",
    ".py",
    ".r",
    ".rb",
    ".rs",
    ".rst",
    ".sass",
    ".scala",
    ".scss",
    ".sh",
    ".sol",
    ".sql",
    ".svelte",
    ".swift",
    ".tex",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
    ".zig",
}
SPECIAL_TEXT_FILENAMES = {
    ".dockerignore",
    ".editorconfig",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    ".npmrc",
    "codeowners",
    "contributing",
    "dockerfile",
    "gemfile",
    "license",
    "makefile",
    "procfile",
    "readme",
}


@dataclass(frozen=True)
class GitHubRepositoryReference:
    owner: str
    repository: str
    url: str
    label: str
    collection_name: str


@dataclass
class GitHubRepositorySnapshot:
    reference: GitHubRepositoryReference
    documents: list[Document]
    archive_sha256: str
    file_count: int
    indexed_bytes: int


def normalize_github_repository_url(url: str) -> GitHubRepositoryReference:
    try:
        parsed = urlparse(url.strip())
    except Exception as exc:
        raise ValueError("Link de repositório GitHub inválido.") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("O link do repositório deve usar HTTP ou HTTPS.")
    if (parsed.hostname or "").lower() not in {"github.com", "www.github.com"}:
        raise ValueError("Somente links de repositórios do GitHub são aceitos.")
    try:
        has_credentials_or_port = bool(
            parsed.username or parsed.password or parsed.port
        )
    except ValueError as exc:
        raise ValueError("Link de repositório GitHub inválido.") from exc
    if has_credentials_or_port:
        raise ValueError("Link de repositório GitHub inválido.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise ValueError("Use o link principal do repositório GitHub.")

    owner, repository = parts
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    if not REPOSITORY_PART_PATTERN.fullmatch(
        owner
    ) or not REPOSITORY_PART_PATTERN.fullmatch(repository):
        raise ValueError("Link de repositório GitHub inválido.")

    normalized_url = f"https://github.com/{owner}/{repository}"
    digest = hashlib.sha256(normalized_url.casefold().encode("utf-8")).hexdigest()
    return GitHubRepositoryReference(
        owner=owner,
        repository=repository,
        url=normalized_url,
        label=f"{owner}/{repository}",
        collection_name=f"github-{digest[:40]}",
    )


def extract_github_repository_urls(messages: list[dict]) -> list[str]:
    repositories: list[str] = []
    seen: set[str] = set()

    for message in messages or []:
        if message.get("role") != "user":
            continue

        content = message.get("content", "")
        if isinstance(content, list):
            text = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        else:
            text = content if isinstance(content, str) else ""

        for match in GITHUB_URL_PATTERN.finditer(text):
            candidate = match.group(0).rstrip(".,;:!?)]}")
            try:
                reference = normalize_github_repository_url(candidate)
            except ValueError:
                continue
            key = reference.url.casefold()
            if key not in seen:
                repositories.append(reference.url)
                seen.add(key)
            if len(repositories) >= MAX_REPOSITORIES_PER_MESSAGE:
                return repositories

    return repositories


def _cache_directory() -> Path:
    directory = Path(CACHE_DIR) / "github_repositories"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _manifest_path(reference: GitHubRepositoryReference) -> Path:
    return _cache_directory() / f"{reference.collection_name}.json"


def load_repository_manifest(reference: GitHubRepositoryReference) -> dict | None:
    path = _manifest_path(reference)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None

    if manifest.get("url") != reference.url:
        return None
    return manifest


def repository_manifest_is_fresh(manifest: dict | None) -> bool:
    if not manifest:
        return False
    try:
        return time.time() - float(manifest.get("indexed_at", 0)) < CACHE_TTL_SECONDS
    except (TypeError, ValueError):
        return False


def save_repository_manifest(snapshot: GitHubRepositorySnapshot) -> None:
    manifest = {
        "url": snapshot.reference.url,
        "label": snapshot.reference.label,
        "collection_name": snapshot.reference.collection_name,
        "archive_sha256": snapshot.archive_sha256,
        "file_count": snapshot.file_count,
        "indexed_bytes": snapshot.indexed_bytes,
        "indexed_at": time.time(),
    }
    path = _manifest_path(snapshot.reference)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(path)


def refresh_repository_manifest(
    reference: GitHubRepositoryReference, manifest: dict
) -> None:
    refreshed = {**manifest, "indexed_at": time.time()}
    path = _manifest_path(reference)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(refreshed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(path)


def _download_repository_archive(reference: GitHubRepositoryReference) -> bytes:
    url = f"{reference.url}/archive/HEAD.zip"
    headers = {
        "Accept": "application/zip",
        "User-Agent": "NeveAI-GitHub-Repository-Reader",
    }
    try:
        response = requests.get(
            url,
            headers=headers,
            stream=True,
            allow_redirects=True,
            timeout=(10, 90),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code == 404:
            raise ValueError(
                "O repositório não foi encontrado ou não é público."
            ) from exc
        raise ValueError("Não foi possível baixar o repositório do GitHub.") from exc

    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > MAX_ARCHIVE_BYTES:
        response.close()
        raise ValueError("O repositório excede o limite de download de 100 MB.")

    archive = io.BytesIO()
    downloaded = 0
    try:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            downloaded += len(chunk)
            if downloaded > MAX_ARCHIVE_BYTES:
                raise ValueError("O repositório excede o limite de download de 100 MB.")
            archive.write(chunk)
    finally:
        response.close()
    return archive.getvalue()


def _repository_path(zip_path: str) -> str | None:
    path = PurePosixPath(zip_path)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
        return None

    relative = PurePosixPath(*path.parts[1:])
    if not relative.parts or any(
        part.casefold() in IGNORED_DIRECTORIES for part in relative.parts[:-1]
    ):
        return None
    return relative.as_posix()


def _is_supported_text_file(path: str, data: bytes) -> bool:
    file_path = PurePosixPath(path)
    filename = file_path.name.casefold()
    stem = file_path.stem.casefold()
    suffix = file_path.suffix.casefold()

    if (
        filename in IGNORED_FILENAMES
        or filename.endswith(".min.js")
        or filename.endswith(".min.css")
    ):
        return False
    if (
        suffix not in TEXT_EXTENSIONS
        and filename not in SPECIAL_TEXT_FILENAMES
        and stem not in SPECIAL_TEXT_FILENAMES
    ):
        return False
    if b"\x00" in data[:8192]:
        return False
    return True


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _source_url(
    reference: GitHubRepositoryReference, path: str, start: int, end: int
) -> str:
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
    return f"{reference.url}/blob/HEAD/{encoded_path}#L{start}-L{end}"


def _chunk_file(
    reference: GitHubRepositoryReference, path: str, text: str
) -> list[Document]:
    lines = text.splitlines()
    if not lines:
        return []

    line_parts: list[tuple[int, str]] = []
    for line_number, line in enumerate(lines, start=1):
        if len(line) <= MAX_CHUNK_CHARS:
            line_parts.append((line_number, line))
            continue
        for offset in range(0, len(line), MAX_CHUNK_CHARS):
            line_parts.append((line_number, line[offset : offset + MAX_CHUNK_CHARS]))

    documents: list[Document] = []
    start_index = 0
    while start_index < len(line_parts):
        end_index = start_index
        char_count = 0
        while end_index < len(line_parts) and end_index - start_index < MAX_CHUNK_LINES:
            next_size = len(line_parts[end_index][1]) + 1
            if end_index > start_index and char_count + next_size > MAX_CHUNK_CHARS:
                break
            char_count += next_size
            end_index += 1

        start_line = line_parts[start_index][0]
        end_line = line_parts[end_index - 1][0]
        body = "\n".join(part for _, part in line_parts[start_index:end_index])
        source = _source_url(reference, path, start_line, end_line)
        documents.append(
            Document(
                page_content=(
                    f"Repository: {reference.label}\n"
                    f"File: {path}\n"
                    f"Lines: {start_line}-{end_line}\n\n{body}"
                ),
                metadata={
                    "name": f"{reference.label}: {path}",
                    "repository": reference.label,
                    "path": path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "source": source,
                    "url": source,
                    "source_type": "github_repository",
                },
            )
        )

        if end_index >= len(line_parts):
            break
        start_index = max(start_index + 1, end_index - CHUNK_OVERLAP_LINES)

    return documents


def load_github_repository(url: str) -> GitHubRepositorySnapshot:
    reference = normalize_github_repository_url(url)
    archive_bytes = _download_repository_archive(reference)
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError(
            "O GitHub retornou um arquivo de repositório inválido."
        ) from exc

    members = [member for member in archive.infolist() if not member.is_dir()]
    if sum(member.file_size for member in members) > MAX_UNCOMPRESSED_BYTES:
        archive.close()
        raise ValueError("O conteúdo do repositório excede o limite permitido.")

    documents: list[Document] = []
    indexed_paths: list[str] = []
    indexed_bytes = 0

    try:
        for member in members:
            if len(indexed_paths) >= MAX_FILES:
                break
            path = _repository_path(member.filename)
            if not path or member.file_size <= 0 or member.file_size > MAX_FILE_BYTES:
                continue

            # Unix symlinks are metadata entries, not repository text.
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                continue

            data = archive.read(member)
            if not _is_supported_text_file(path, data):
                continue
            if indexed_bytes + len(data) > MAX_INDEXED_BYTES:
                break

            text = _decode_text(data).strip("\ufeff")
            if not text.strip():
                continue
            line_count = max(1, text.count("\n") + 1)
            if len(text) > 20_000 and len(text) / line_count > 1_500:
                continue

            file_documents = _chunk_file(reference, path, text)
            if not file_documents:
                continue
            documents.extend(file_documents)
            indexed_paths.append(path)
            indexed_bytes += len(data)
    finally:
        archive.close()

    if not documents:
        raise ValueError(
            "Nenhum arquivo de texto compatível foi encontrado no repositório."
        )

    map_source = f"{reference.url}/tree/HEAD"
    map_documents = []
    current_paths = []
    current_size = 0
    for path in indexed_paths:
        if current_paths and current_size + len(path) + 1 > MAX_CHUNK_CHARS:
            map_documents.append(current_paths)
            current_paths = []
            current_size = 0
        current_paths.append(path)
        current_size += len(path) + 1
    if current_paths:
        map_documents.append(current_paths)

    for index, paths in reversed(list(enumerate(map_documents, start=1))):
        documents.insert(
            0,
            Document(
                page_content=(
                    f"Repository: {reference.label}\n"
                    f"Repository file map, part {index}/{len(map_documents)} "
                    f"({len(indexed_paths)} indexed files):\n" + "\n".join(paths)
                ),
                metadata={
                    "name": f"{reference.label}: repository map",
                    "repository": reference.label,
                    "path": "",
                    "source": map_source,
                    "url": map_source,
                    "source_type": "github_repository",
                },
            ),
        )

    return GitHubRepositorySnapshot(
        reference=reference,
        documents=documents,
        archive_sha256=archive_sha256,
        file_count=len(indexed_paths),
        indexed_bytes=indexed_bytes,
    )
