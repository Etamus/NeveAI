import json
import logging
import mimetypes
import os
import shutil
import asyncio

import re
import time
import uuid
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from datetime import datetime
from typing import (List, Optional)

from fastapi import (Depends, Query, HTTPException, Request, status, APIRouter)
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import tiktoken


from langchain_core.documents import Document

from neveai.models.files import FileModel, FileUpdateForm, Files
from neveai.utils.access_control.files import has_access_to_file
from neveai.models.knowledge import Knowledges
from neveai.storage.provider import Storage
from neveai.internal.db import get_session, get_db
from sqlalchemy.orm import Session


from neveai.retrieval.vector.factory import VECTOR_DB_CLIENT
from neveai.retrieval.github import (
    load_github_repository,
    load_repository_manifest,
    normalize_github_repository_url,
    refresh_repository_manifest,
    repository_manifest_has_current_schema,
    repository_manifest_is_fresh,
    save_repository_manifest,
)

from neveai.retrieval.web.main import SearchResult
from neveai.retrieval.web.duckduckgo import search_duckduckgo
from neveai.retrieval.web.searxng import search_searxng

from neveai.retrieval.utils import (
    get_content_from_url,
    get_embedding_function,
    get_reranking_function,
    get_model_path,
    query_collection,
    query_collection_with_hybrid_search,
    query_doc,
    query_doc_with_hybrid_search,
)
from neveai.retrieval.vector.utils import filter_metadata
from neveai.utils.misc import (
    calculate_sha256_string,
    sanitize_text_for_db,
)
from neveai.utils.auth import get_admin_user, get_verified_user
from neveai.utils.access_control import has_permission

from neveai.config import (ENV, RAG_EMBEDDING_MODEL_AUTO_UPDATE, RAG_EMBEDDING_MODEL_TRUST_REMOTE_CODE, RAG_RERANKING_MODEL_AUTO_UPDATE, RAG_RERANKING_MODEL_TRUST_REMOTE_CODE, UPLOAD_DIR, RAG_EMBEDDING_CONTENT_PREFIX, RAG_EMBEDDING_QUERY_PREFIX)
from neveai.env import (
    DEVICE_TYPE,
    RAG_EMBEDDING_TIMEOUT,
    SENTENCE_TRANSFORMERS_BACKEND,
    SENTENCE_TRANSFORMERS_MODEL_KWARGS,
    SENTENCE_TRANSFORMERS_CROSS_ENCODER_BACKEND,
    SENTENCE_TRANSFORMERS_CROSS_ENCODER_MODEL_KWARGS,
    SENTENCE_TRANSFORMERS_CROSS_ENCODER_SIGMOID_ACTIVATION_FUNCTION,
)

from neveai.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)

SEARXNG_PUBLIC_QUERY_URLS = (
    "https://searx.tiekoetter.com/search",
    "https://searx.linxx.net/search",
    "https://searxng.website/search",
    "https://search.bladerunn.in/search",
    "https://baresearch.org/search",
)
SEARXNG_LOCAL_QUERY_URLS = (
    "http://127.0.0.1:8888/search",
    "http://127.0.0.1:8081/search",
)
SEARXNG_FAST_ENGINES = ("duckduckgo", "qwant")
SEARXNG_DEEP_ENGINES = ("duckduckgo", "qwant", "bing", "brave", "mojeek")
SEARXNG_FAST_TIMEOUT = 3
SEARXNG_DEEP_TIMEOUT = 7
DDGS_FAST_TIMEOUT = 8
DDGS_DEEP_TIMEOUT = 15
SEARXNG_FAILURE_BACKOFF_SECONDS = 180
SEARXNG_UNAVAILABLE_UNTIL: dict[str, float] = {}

##########################################
#
# Utility functions
#
##########################################


def get_ef(
    engine: str,
    embedding_model: str,
    auto_update: bool = RAG_EMBEDDING_MODEL_AUTO_UPDATE,
):
    ef = None
    if embedding_model and engine == "":
        from sentence_transformers import SentenceTransformer

        try:
            ef = SentenceTransformer(
                get_model_path(embedding_model, auto_update),
                device=DEVICE_TYPE,
                trust_remote_code=RAG_EMBEDDING_MODEL_TRUST_REMOTE_CODE,
                backend=SENTENCE_TRANSFORMERS_BACKEND,
                model_kwargs=SENTENCE_TRANSFORMERS_MODEL_KWARGS,
            )
        except Exception as e:
            log.debug(f"Error loading SentenceTransformer: {e}")

    return ef


def get_rf(
    reranking_model: Optional[str] = None,
    auto_update: bool = RAG_RERANKING_MODEL_AUTO_UPDATE,
):
    rf = None
    if reranking_model:
        import sentence_transformers
        import torch

        try:
            rf = sentence_transformers.CrossEncoder(
                get_model_path(reranking_model, auto_update),
                device=DEVICE_TYPE,
                trust_remote_code=RAG_RERANKING_MODEL_TRUST_REMOTE_CODE,
                backend=SENTENCE_TRANSFORMERS_CROSS_ENCODER_BACKEND,
                model_kwargs=SENTENCE_TRANSFORMERS_CROSS_ENCODER_MODEL_KWARGS,
                activation_fn=(
                    torch.nn.Sigmoid()
                    if SENTENCE_TRANSFORMERS_CROSS_ENCODER_SIGMOID_ACTIVATION_FUNCTION
                    else None
                ),
            )
        except Exception as e:
            log.error(f"CrossEncoder: {e}")
            raise Exception(ERROR_MESSAGES.DEFAULT("CrossEncoder error"))

        try:
            model_cfg = getattr(rf, "model", None)
            if model_cfg and hasattr(model_cfg, "config"):
                cfg = model_cfg.config
                if getattr(cfg, "pad_token_id", None) is None:
                    eos = getattr(cfg, "eos_token_id", None)
                    if eos is not None:
                        cfg.pad_token_id = eos
        except Exception as error:
            log.warning(f"Failed to adjust pad_token_id on CrossEncoder: {error}")

    return rf


##########################################
#
# API routes
#
##########################################


router = APIRouter()


class CollectionNameForm(BaseModel):
    collection_name: Optional[str] = None


class ProcessUrlForm(CollectionNameForm):
    url: str


class SearchForm(BaseModel):
    queries: List[str]
    engine: Optional[str] = None
    result_count: Optional[int] = None
    max_loaded_urls: Optional[int] = None
    urls: List[str] = []
    search_after_urls: bool = False
    question: str = ""


@router.get("/")
async def get_status(request: Request):
    return {
        "status": True,
        "CHUNK_SIZE": request.app.state.config.CHUNK_SIZE,
        "CHUNK_OVERLAP": request.app.state.config.CHUNK_OVERLAP,
        "RAG_TEMPLATE": request.app.state.config.RAG_TEMPLATE,
        "RAG_EMBEDDING_ENGINE": request.app.state.config.RAG_EMBEDDING_ENGINE,
        "RAG_EMBEDDING_MODEL": request.app.state.config.RAG_EMBEDDING_MODEL,
        "RAG_RERANKING_MODEL": request.app.state.config.RAG_RERANKING_MODEL,
        "RAG_EMBEDDING_BATCH_SIZE": request.app.state.config.RAG_EMBEDDING_BATCH_SIZE,
        "ENABLE_ASYNC_EMBEDDING": request.app.state.config.ENABLE_ASYNC_EMBEDDING,
        "RAG_EMBEDDING_CONCURRENT_REQUESTS": request.app.state.config.RAG_EMBEDDING_CONCURRENT_REQUESTS,
    }


####################################
#
# Document process and retrieval
#
####################################


def can_merge_chunks(a: Document, b: Document) -> bool:
    if a.metadata.get("source") != b.metadata.get("source"):
        return False

    a_file_id = a.metadata.get("file_id")
    b_file_id = b.metadata.get("file_id")

    if a_file_id is not None and b_file_id is not None:
        return a_file_id == b_file_id

    return True


def merge_docs_to_target_size(
    request: Request,
    chunks: list[Document],
) -> list[Document]:
    """
    Best-effort normalization of chunk sizes.

    Attempts to grow small chunks up to a desired minimum size,
    without exceeding the maximum size or crossing source/file
    boundaries.
    """
    min_chunk_size_target = request.app.state.config.CHUNK_MIN_SIZE_TARGET
    max_chunk_size = request.app.state.config.CHUNK_SIZE

    if min_chunk_size_target <= 0:
        return chunks

    measure_chunk_size = len
    if request.app.state.config.TEXT_SPLITTER == "token":
        encoding = tiktoken.get_encoding(
            str(request.app.state.config.TIKTOKEN_ENCODING_NAME)
        )
        measure_chunk_size = lambda text: len(encoding.encode(text))

    processed_chunks: list[Document] = []

    current_chunk: Document | None = None
    current_content: str = ""

    for next_chunk in chunks:
        if current_chunk is None:
            current_chunk = next_chunk
            current_content = next_chunk.page_content
            continue  # First chunk initialization

        proposed_content = f"{current_content}\n\n{next_chunk.page_content}"

        can_merge = (
            can_merge_chunks(current_chunk, next_chunk)
            and measure_chunk_size(current_content) < min_chunk_size_target
            and measure_chunk_size(proposed_content) <= max_chunk_size
        )

        if can_merge:
            current_content = proposed_content
        else:
            processed_chunks.append(
                Document(
                    page_content=current_content,
                    metadata={**current_chunk.metadata},
                )
            )
            current_chunk = next_chunk
            current_content = next_chunk.page_content

    if current_chunk is not None:
        processed_chunks.append(
            Document(
                page_content=current_content,
                metadata={**current_chunk.metadata},
            )
        )

    return processed_chunks


def save_docs_to_vector_db(
    request: Request,
    docs,
    collection_name,
    metadata: Optional[dict] = None,
    overwrite: bool = False,
    split: bool = True,
    add: bool = False,
    user=None,
) -> bool:
    from langchain_text_splitters import (
        MarkdownHeaderTextSplitter,
        RecursiveCharacterTextSplitter,
        TokenTextSplitter,
    )

    def _get_docs_info(docs: list[Document]) -> str:
        docs_info = set()

        # Trying to select relevant metadata identifying the document.
        for doc in docs:
            metadata = getattr(doc, "metadata", {})
            doc_name = metadata.get("name", "")
            if not doc_name:
                doc_name = metadata.get("title", "")
            if not doc_name:
                doc_name = metadata.get("source", "")
            if doc_name:
                docs_info.add(doc_name)

        return ", ".join(docs_info)

    log.debug(
        f"save_docs_to_vector_db: document {_get_docs_info(docs)} {collection_name}"
    )

    # Check if entries with the same hash (metadata.hash) already exist
    if metadata and "hash" in metadata:
        result = VECTOR_DB_CLIENT.query(
            collection_name=collection_name,
            filter={"hash": metadata["hash"]},
        )

        if result is not None and result.ids and len(result.ids) > 0:
            existing_doc_ids = result.ids[0]
            if existing_doc_ids:
                # Check if the existing document belongs to the same file
                # If same file_id, this is a re-add/reindex - allow it
                # If different file_id, this is a duplicate - block it
                existing_file_id = None
                if result.metadatas and result.metadatas[0]:
                    existing_file_id = result.metadatas[0][0].get("file_id")

                if existing_file_id != metadata.get("file_id"):
                    log.info(f"Document with hash {metadata['hash']} already exists")
                    raise ValueError(ERROR_MESSAGES.DUPLICATE_CONTENT)

    if split:
        if request.app.state.config.ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER:
            log.info("Using markdown header text splitter")
            # Define headers to split on - covering most common markdown header levels
            markdown_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[
                    ("#", "Header 1"),
                    ("##", "Header 2"),
                    ("###", "Header 3"),
                    ("####", "Header 4"),
                    ("#####", "Header 5"),
                    ("######", "Header 6"),
                ],
                strip_headers=False,  # Keep headers in content for context
            )

            split_docs = []
            for doc in docs:
                split_docs.extend(
                    [
                        Document(
                            page_content=split_chunk.page_content,
                            metadata={**doc.metadata},
                        )
                        for split_chunk in markdown_splitter.split_text(
                            doc.page_content
                        )
                    ]
                )

            docs = split_docs
            if request.app.state.config.CHUNK_MIN_SIZE_TARGET > 0:
                docs = merge_docs_to_target_size(request, docs)

        if request.app.state.config.TEXT_SPLITTER in ["", "character"]:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=request.app.state.config.CHUNK_SIZE,
                chunk_overlap=request.app.state.config.CHUNK_OVERLAP,
                add_start_index=True,
            )
            docs = text_splitter.split_documents(docs)
        elif request.app.state.config.TEXT_SPLITTER == "token":
            log.info(
                f"Using token text splitter: {request.app.state.config.TIKTOKEN_ENCODING_NAME}"
            )

            tiktoken.get_encoding(str(request.app.state.config.TIKTOKEN_ENCODING_NAME))
            text_splitter = TokenTextSplitter(
                encoding_name=str(request.app.state.config.TIKTOKEN_ENCODING_NAME),
                chunk_size=request.app.state.config.CHUNK_SIZE,
                chunk_overlap=request.app.state.config.CHUNK_OVERLAP,
                add_start_index=True,
            )
            docs = text_splitter.split_documents(docs)
        else:
            raise ValueError(ERROR_MESSAGES.DEFAULT("Invalid text splitter"))

    if len(docs) == 0:
        raise ValueError(ERROR_MESSAGES.EMPTY_CONTENT)

    texts = [sanitize_text_for_db(doc.page_content) for doc in docs]
    metadatas = [
        {
            **doc.metadata,
            **(metadata if metadata else {}),
            "embedding_config": {
                "engine": request.app.state.config.RAG_EMBEDDING_ENGINE,
                "model": request.app.state.config.RAG_EMBEDDING_MODEL,
            },
        }
        for doc in docs
    ]

    try:
        if VECTOR_DB_CLIENT.has_collection(collection_name=collection_name):
            log.info(f"collection {collection_name} already exists")

            if overwrite:
                VECTOR_DB_CLIENT.delete_collection(collection_name=collection_name)
                log.info(f"deleting existing collection {collection_name}")
            elif add is False:
                log.info(
                    f"collection {collection_name} already exists, overwrite is False and add is False"
                )
                return True

        log.info(f"generating embeddings for {collection_name}")
        embedding_function = get_embedding_function(
            request.app.state.ef,
            request.app.state.config.RAG_EMBEDDING_BATCH_SIZE,
        )

        # Run async embedding in sync context using the main event loop
        # This allows the main loop to stay responsive to health checks during long operations
        embedding_timeout = RAG_EMBEDDING_TIMEOUT

        future = asyncio.run_coroutine_threadsafe(
            embedding_function(
                list(map(lambda x: x.replace("\n", " "), texts)),
                prefix=RAG_EMBEDDING_CONTENT_PREFIX,
                user=user,
            ),
            request.app.state.main_loop,
        )
        embeddings = future.result(timeout=embedding_timeout)
        log.info(f"embeddings generated {len(embeddings)} for {len(texts)} items")

        items = [
            {
                "id": str(uuid.uuid4()),
                "text": text,
                "vector": embeddings[idx],
                "metadata": metadatas[idx],
            }
            for idx, text in enumerate(texts)
        ]

        log.info(f"adding to collection {collection_name}")
        VECTOR_DB_CLIENT.insert(
            collection_name=collection_name,
            items=items,
        )

        log.info(f"added {len(items)} items to collection {collection_name}")
        return True
    except Exception as e:
        log.exception(e)
        raise e


class ProcessFileForm(BaseModel):
    file_id: str
    content: Optional[str] = None
    collection_name: Optional[str] = None


@router.post("/process/file")
def process_file(
    request: Request,
    form_data: ProcessFileForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """
    Process a file and save its content to the vector database.
    Process a file and save its content to the vector database.
    Note: granular session management is used to prevent connection pool exhaustion.
    The session is committed before external API calls, and updates use a fresh session.
    """
    if user.role == "admin":
        file = Files.get_file_by_id(form_data.file_id, db=db)
    else:
        file = Files.get_file_by_id_and_user_id(form_data.file_id, user.id, db=db)

    if file:
        try:

            collection_name = form_data.collection_name

            if collection_name is None:
                collection_name = f"file-{file.id}"

            if form_data.content:
                # Update the content in the file
                # Usage: /files/{file_id}/data/content/update, /files/ (audio file upload pipeline)

                try:
                    # /files/{file_id}/data/content/update
                    VECTOR_DB_CLIENT.delete_collection(
                        collection_name=f"file-{file.id}"
                    )
                except:
                    # Audio file upload pipeline
                    pass

                docs = [
                    Document(
                        page_content=form_data.content.replace("<br/>", "\n"),
                        metadata={
                            **file.meta,
                            "name": file.filename,
                            "created_by": file.user_id,
                            "file_id": file.id,
                            "source": file.filename,
                        },
                    )
                ]

                text_content = form_data.content
            elif form_data.collection_name:
                # Check if the file has already been processed and save the content
                # Usage: /knowledge/{id}/file/add, /knowledge/{id}/file/update

                result = VECTOR_DB_CLIENT.query(
                    collection_name=f"file-{file.id}", filter={"file_id": file.id}
                )

                if result is not None and len(result.ids[0]) > 0:
                    docs = [
                        Document(
                            page_content=result.documents[0][idx],
                            metadata=result.metadatas[0][idx],
                        )
                        for idx, id in enumerate(result.ids[0])
                    ]
                else:
                    docs = [
                        Document(
                            page_content=file.data.get("content", ""),
                            metadata={
                                **file.meta,
                                "name": file.filename,
                                "created_by": file.user_id,
                                "file_id": file.id,
                                "source": file.filename,
                            },
                        )
                    ]

                text_content = file.data.get("content", "")
            else:
                # Process the file and save the content
                # Usage: /files/
                file_path = file.path
                if file_path:
                    from neveai.retrieval.loaders.main import Loader

                    file_path = Storage.get_file(file_path)
                    loader = Loader(
                        PDF_EXTRACT_IMAGES=request.app.state.config.PDF_EXTRACT_IMAGES,
                        PDF_LOADER_MODE=request.app.state.config.PDF_LOADER_MODE,
                    )
                    docs = loader.load(
                        file.filename, file.meta.get("content_type"), file_path
                    )

                    docs = [
                        Document(
                            page_content=doc.page_content,
                            metadata={
                                **filter_metadata(doc.metadata),
                                "name": file.filename,
                                "created_by": file.user_id,
                                "file_id": file.id,
                                "source": file.filename,
                            },
                        )
                        for doc in docs
                    ]
                else:
                    docs = [
                        Document(
                            page_content=file.data.get("content", ""),
                            metadata={
                                **file.meta,
                                "name": file.filename,
                                "created_by": file.user_id,
                                "file_id": file.id,
                                "source": file.filename,
                            },
                        )
                    ]
                text_content = " ".join([doc.page_content for doc in docs])

            log.debug(f"text_content: {text_content}")
            Files.update_file_data_by_id(
                file.id,
                {"content": text_content},
                db=db,
            )
            hash = calculate_sha256_string(text_content)

            if request.app.state.config.BYPASS_EMBEDDING_AND_RETRIEVAL:
                Files.update_file_data_by_id(file.id, {"status": "completed"}, db=db)
                Files.update_file_hash_by_id(file.id, hash, db=db)
                return {
                    "status": True,
                    "collection_name": None,
                    "filename": file.filename,
                    "content": text_content,
                }
            else:
                try:
                    # Commit any pending changes before the slow embedding step.
                    # Note: file is already a Pydantic model (not ORM), so no expunge needed.
                    db.commit()

                    # External embedding API takes time (5-60s+).
                    # Subsequent updates use fresh sessions via get_db().
                    result = save_docs_to_vector_db(
                        request,
                        docs=docs,
                        collection_name=collection_name,
                        metadata={
                            "file_id": file.id,
                            "name": file.filename,
                            "hash": hash,
                        },
                        add=(True if form_data.collection_name else False),
                        user=user,
                    )
                    log.info(f"added {len(docs)} items to collection {collection_name}")

                    if result:
                        # Fresh session for the final update.
                        with get_db() as session:
                            Files.update_file_metadata_by_id(
                                file.id,
                                {
                                    "collection_name": collection_name,
                                },
                                db=session,
                            )

                            Files.update_file_data_by_id(
                                file.id,
                                {"status": "completed"},
                                db=session,
                            )
                            Files.update_file_hash_by_id(file.id, hash, db=session)

                            return {
                                "status": True,
                                "collection_name": collection_name,
                                "filename": file.filename,
                                "content": text_content,
                            }
                    else:
                        raise Exception("Error saving document to vector database")
                except Exception as e:
                    raise e

        except Exception as e:
            log.exception(e)
            # Fresh session for error status update.
            with get_db() as session:
                Files.update_file_data_by_id(
                    file.id,
                    {"status": "failed"},
                    db=session,
                )
                # Clear the hash so the file can be re-uploaded after fixing the issue
                Files.update_file_hash_by_id(file.id, None, db=session)

            if "No pandoc was found" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.PANDOC_NOT_INSTALLED,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                )

    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )


class ProcessTextForm(BaseModel):
    name: str
    content: str
    collection_name: Optional[str] = None


@router.post("/process/text")
async def process_text(
    request: Request,
    form_data: ProcessTextForm,
    user=Depends(get_verified_user),
):
    collection_name = form_data.collection_name
    if collection_name is None:
        collection_name = calculate_sha256_string(form_data.content)

    docs = [
        Document(
            page_content=form_data.content,
            metadata={"name": form_data.name, "created_by": user.id},
        )
    ]
    text_content = form_data.content
    log.debug(f"text_content: {text_content}")

    result = await run_in_threadpool(
        save_docs_to_vector_db, request, docs, collection_name, user=user
    )
    if result:
        return {
            "status": True,
            "collection_name": collection_name,
            "content": text_content,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(),
        )


_GITHUB_REPOSITORY_LOCKS: dict[str, asyncio.Lock] = {}


async def index_github_repository(request: Request, url: str, user=None) -> dict:
    reference = normalize_github_repository_url(url)
    manifest = load_repository_manifest(reference)
    collection_exists = VECTOR_DB_CLIENT.has_collection(
        collection_name=reference.collection_name
    )

    if collection_exists and repository_manifest_is_fresh(manifest):
        return {
            "status": True,
            "cached": True,
            "collection_name": reference.collection_name,
            "filename": reference.label,
            "url": reference.url,
            "file_count": manifest.get("file_count", 0),
        }

    lock = _GITHUB_REPOSITORY_LOCKS.setdefault(reference.collection_name, asyncio.Lock())
    async with lock:
        manifest = load_repository_manifest(reference)
        collection_exists = VECTOR_DB_CLIENT.has_collection(
            collection_name=reference.collection_name
        )
        if collection_exists and repository_manifest_is_fresh(manifest):
            return {
                "status": True,
                "cached": True,
                "collection_name": reference.collection_name,
                "filename": reference.label,
                "url": reference.url,
                "file_count": manifest.get("file_count", 0),
            }

        snapshot = await run_in_threadpool(load_github_repository, reference.url)
        if (
            collection_exists
            and manifest
            and repository_manifest_has_current_schema(manifest)
            and manifest.get("archive_sha256") == snapshot.archive_sha256
        ):
            refresh_repository_manifest(reference, manifest)
            return {
                "status": True,
                "cached": True,
                "collection_name": reference.collection_name,
                "filename": reference.label,
                "url": reference.url,
                "file_count": manifest.get("file_count", snapshot.file_count),
            }

        if request.app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL:
            return {
                "status": True,
                "cached": False,
                "collection_name": None,
                "filename": reference.label,
                "url": reference.url,
                "file_count": snapshot.file_count,
                "docs": [
                    {"content": doc.page_content, "metadata": doc.metadata}
                    for doc in snapshot.documents
                ],
            }

        await run_in_threadpool(
            save_docs_to_vector_db,
            request,
            snapshot.documents,
            reference.collection_name,
            metadata={
                "repository": reference.label,
                "repository_url": reference.url,
                "archive_sha256": snapshot.archive_sha256,
            },
            overwrite=True,
            split=False,
            user=user,
        )
        save_repository_manifest(snapshot)

        return {
            "status": True,
            "cached": False,
            "collection_name": reference.collection_name,
            "filename": reference.label,
            "url": reference.url,
            "file_count": snapshot.file_count,
        }


@router.post("/process/github")
async def process_github_repository(
    request: Request,
    form_data: ProcessUrlForm,
    user=Depends(get_verified_user),
):
    try:
        return await index_github_repository(request, form_data.url, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("GitHub repository processing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível analisar o repositório GitHub.",
        ) from exc


@router.post("/process/youtube")
@router.post("/process/web")
async def process_web(
    request: Request,
    form_data: ProcessUrlForm,
    process: bool = Query(True, description="Whether to process and save the content"),
    overwrite: bool = Query(
        True, description="Whether to overwrite existing collection"
    ),
    user=Depends(get_verified_user),
):
    try:
        content, docs = await run_in_threadpool(
            get_content_from_url, request, form_data.url
        )
        log.debug(f"text_content: {content}")

        if process:
            collection_name = form_data.collection_name
            if not collection_name:
                collection_name = calculate_sha256_string(form_data.url)[:63]

            if not request.app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL:
                await run_in_threadpool(
                    save_docs_to_vector_db,
                    request,
                    docs,
                    collection_name,
                    overwrite=overwrite,
                    add=(not overwrite),
                    user=user,
                )
            else:
                collection_name = None

            return {
                "status": True,
                "collection_name": collection_name,
                "filename": form_data.url,
                "file": {
                    "data": {
                        "content": content,
                    },
                    "meta": {
                        "name": form_data.url,
                        "source": form_data.url,
                    },
                },
            }
        else:
            return {
                "status": True,
                "content": content,
            }
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


def search_web(
    request: Request,
    engine: str,
    query: str,
    user=None,
    result_count: Optional[int] = None,
) -> list[SearchResult]:
    """Search through SearXNG with the local DDGS fallback."""

    result_count = result_count or request.app.state.config.WEB_SEARCH_RESULT_COUNT

    def get_free_search_profile() -> dict:
        deep_search_enabled = bool(getattr(request.state, "deep_search_enabled", False))
        if deep_search_enabled:
            return {
                "count": min(max(result_count or 20, 10), 20),
                "engines": SEARXNG_DEEP_ENGINES,
                "searxng_timeout": SEARXNG_DEEP_TIMEOUT,
                "ddgs_timeout": DDGS_DEEP_TIMEOUT,
                "public_url_limit": 0,
            }

        return {
            "count": min(result_count or 5, 5),
            "engines": SEARXNG_FAST_ENGINES,
            "searxng_timeout": SEARXNG_FAST_TIMEOUT,
            "ddgs_timeout": DDGS_FAST_TIMEOUT,
            "public_url_limit": 0,
        }

    def get_searxng_query_urls(public_url_limit: int) -> list[str]:
        urls = []
        configured_url = request.app.state.config.SEARXNG_QUERY_URL or ""
        for raw_url in re.split(r"[\s,]+", configured_url.strip()):
            if raw_url:
                urls.append(raw_url)

        urls.extend(SEARXNG_LOCAL_QUERY_URLS)
        urls.extend(SEARXNG_PUBLIC_QUERY_URLS[:public_url_limit])

        unique_urls = []
        seen_urls = set()
        now = time.monotonic()
        for url in urls:
            normalized_url = url.strip()
            if not normalized_url or normalized_url in seen_urls:
                continue
            if SEARXNG_UNAVAILABLE_UNTIL.get(normalized_url, 0) > now:
                continue
            unique_urls.append(normalized_url)
            seen_urls.add(normalized_url)

        return unique_urls

    def mark_searxng_unavailable(query_url: str, error: Exception | None = None) -> None:
        if not error:
            return

        error_text = str(error).lower()
        should_backoff = any(
            token in error_text
            for token in ("403", "429", "too many", "timeout", "timed out")
        ) or any(
            token in error_text
            for token in ("connection refused", "failed to establish", "max retries")
        )
        if should_backoff:
            SEARXNG_UNAVAILABLE_UNTIL[query_url] = (
                time.monotonic() + SEARXNG_FAILURE_BACKOFF_SECONDS
            )

    def search_searxng_then_ddgs() -> list[SearchResult]:
        profile = get_free_search_profile()
        search_count = profile["count"]
        searxng_errors = []
        query_urls = get_searxng_query_urls(profile["public_url_limit"])

        def run_searxng_query(query_url: str) -> list[SearchResult]:
            return search_searxng(
                query_url,
                query,
                search_count,
                request.app.state.config.WEB_SEARCH_DOMAIN_FILTER_LIST,
                language=request.app.state.config.SEARXNG_LANGUAGE,
                engines=profile["engines"],
                timeout=profile["searxng_timeout"],
            )

        if query_urls:
            executor = ThreadPoolExecutor(max_workers=len(query_urls))
            futures = {
                executor.submit(run_searxng_query, query_url): query_url
                for query_url in query_urls
            }
            try:
                for future in as_completed(
                    futures,
                    timeout=profile["searxng_timeout"] + 1,
                ):
                    query_url = futures[future]
                    try:
                        results = future.result()
                        if results:
                            executor.shutdown(wait=False, cancel_futures=True)
                            return results[:search_count]

                        searxng_errors.append(f"{query_url}: no results")
                    except Exception as e:
                        mark_searxng_unavailable(query_url, e)
                        searxng_errors.append(f"{query_url}: {e}")
            except FuturesTimeoutError:
                for query_url in query_urls:
                    SEARXNG_UNAVAILABLE_UNTIL[query_url] = (
                        time.monotonic() + SEARXNG_FAILURE_BACKOFF_SECONDS
                    )
                searxng_errors.append("SearXNG timeout")
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        ddgs_results = search_duckduckgo(
            query,
            search_count,
            request.app.state.config.WEB_SEARCH_DOMAIN_FILTER_LIST,
            concurrent_requests=request.app.state.config.WEB_SEARCH_CONCURRENT_REQUESTS,
            backend=request.app.state.config.DDGS_BACKEND,
            timeout=profile["ddgs_timeout"],
        )
        if searxng_errors and not ddgs_results:
            log.warning(
                "SearXNG and DDGS returned no results. %s",
                " | ".join(searxng_errors[-3:]),
            )
        elif searxng_errors:
            log.debug(
                "SearXNG unavailable; DDGS fallback returned results. %s",
                " | ".join(searxng_errors[-3:]),
            )

        return ddgs_results

    normalized_engine = (engine or "duckduckgo").lower()
    if normalized_engine == "searxng":
        return search_searxng_then_ddgs()

    if normalized_engine not in {"duckduckgo", "ddgs"}:
        log.warning(
            "Unsupported legacy web search engine '%s'; using the local free-search pipeline",
            engine,
        )
        return search_searxng_then_ddgs()

    return search_duckduckgo(
        query,
        result_count,
        request.app.state.config.WEB_SEARCH_DOMAIN_FILTER_LIST,
        concurrent_requests=request.app.state.config.WEB_SEARCH_CONCURRENT_REQUESTS,
        backend=request.app.state.config.DDGS_BACKEND,
        timeout=DDGS_DEEP_TIMEOUT
        if bool(getattr(request.state, "deep_search_enabled", False))
        else DDGS_FAST_TIMEOUT,
    )

@router.post("/process/web/search")
async def process_web_search(
    request: Request, form_data: SearchForm, user=Depends(get_verified_user)
):
    if not request.app.state.config.ENABLE_WEB_SEARCH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if user.role != "admin" and not has_permission(
        user.id, "features.web_search", request.app.state.config.USER_PERMISSIONS
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    from neveai.retrieval.web.research import research

    deep = bool(getattr(request.state, "deep_search_enabled", False))
    configured_limit = request.app.state.config.WEB_SEARCH_CONCURRENT_REQUESTS
    semaphore = asyncio.Semaphore(max(1, min(configured_limit or 3, 3)))

    async def bounded_search(engine, count):
        async def query_search(query):
            try:
                async with semaphore:
                    return await asyncio.wait_for(
                        run_in_threadpool(search_web, request, engine, query, user, count),
                        timeout=20,
                    )
            except Exception as error:
                log.warning("Search failed for %s: %s", query, error)
                return []

        tasks = [asyncio.create_task(query_search(query)) for query in form_data.queries[:3]]
        if not tasks:
            return []
        try:
            # Keep completed evidence even when another query stalls.
            done, _ = await asyncio.wait(tasks, timeout=22 if deep else 20)
            return [item for task in tasks if task in done for item in task.result()]
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return await research(request, form_data, user, bounded_search)


def _validate_collection_access(collection_names: list[str], user) -> None:
    """
    Prevent users from querying collections they don't own.
    Enforces ownership on user-memory-* and file-* collections.
    Admins bypass this check.
    """
    if user.role == "admin":
        return

    for name in collection_names:
        if name.startswith("user-memory-") and name != f"user-memory-{user.id}":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )
        elif name.startswith("file-"):
            file_id = name[len("file-") :]
            if not has_access_to_file(
                file_id=file_id,
                access_type="read",
                user=user,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
                )


class QueryDocForm(BaseModel):
    collection_name: str
    query: str
    k: Optional[int] = None
    k_reranker: Optional[int] = None
    r: Optional[float] = None
    hybrid: Optional[bool] = None


@router.post("/query/doc")
async def query_doc_handler(
    request: Request,
    form_data: QueryDocForm,
    user=Depends(get_verified_user),
):
    _validate_collection_access([form_data.collection_name], user)

    try:
        if request.app.state.config.ENABLE_RAG_HYBRID_SEARCH and (
            form_data.hybrid is None or form_data.hybrid
        ):
            collection_results = {}
            collection_results[form_data.collection_name] = VECTOR_DB_CLIENT.get(
                collection_name=form_data.collection_name
            )
            return await query_doc_with_hybrid_search(
                collection_name=form_data.collection_name,
                collection_result=collection_results[form_data.collection_name],
                query=form_data.query,
                embedding_function=lambda query, prefix: request.app.state.EMBEDDING_FUNCTION(
                    query, prefix=prefix, user=user
                ),
                k=form_data.k if form_data.k else request.app.state.config.TOP_K,
                reranking_function=(
                    (
                        lambda query, documents: request.app.state.RERANKING_FUNCTION(
                            query, documents, user=user
                        )
                    )
                    if request.app.state.RERANKING_FUNCTION
                    else None
                ),
                k_reranker=form_data.k_reranker
                or request.app.state.config.TOP_K_RERANKER,
                r=(
                    form_data.r
                    if form_data.r
                    else request.app.state.config.RELEVANCE_THRESHOLD
                ),
                hybrid_bm25_weight=(
                    form_data.hybrid_bm25_weight
                    if form_data.hybrid_bm25_weight
                    else request.app.state.config.HYBRID_BM25_WEIGHT
                ),
                user=user,
            )
        else:
            query_embedding = await request.app.state.EMBEDDING_FUNCTION(
                form_data.query, prefix=RAG_EMBEDDING_QUERY_PREFIX, user=user
            )
            return query_doc(
                collection_name=form_data.collection_name,
                query_embedding=query_embedding,
                k=form_data.k if form_data.k else request.app.state.config.TOP_K,
                user=user,
            )
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


class QueryCollectionsForm(BaseModel):
    collection_names: list[str]
    query: str
    k: Optional[int] = None
    k_reranker: Optional[int] = None
    r: Optional[float] = None
    hybrid: Optional[bool] = None
    hybrid_bm25_weight: Optional[float] = None
    enable_enriched_texts: Optional[bool] = None


@router.post("/query/collection")
async def query_collection_handler(
    request: Request,
    form_data: QueryCollectionsForm,
    user=Depends(get_verified_user),
):
    _validate_collection_access(form_data.collection_names, user)

    try:
        if request.app.state.config.ENABLE_RAG_HYBRID_SEARCH and (
            form_data.hybrid is None or form_data.hybrid
        ):
            return await query_collection_with_hybrid_search(
                collection_names=form_data.collection_names,
                queries=[form_data.query],
                embedding_function=lambda query, prefix: request.app.state.EMBEDDING_FUNCTION(
                    query, prefix=prefix, user=user
                ),
                k=form_data.k if form_data.k else request.app.state.config.TOP_K,
                reranking_function=(
                    (
                        lambda query, documents: request.app.state.RERANKING_FUNCTION(
                            query, documents, user=user
                        )
                    )
                    if request.app.state.RERANKING_FUNCTION
                    else None
                ),
                k_reranker=form_data.k_reranker
                or request.app.state.config.TOP_K_RERANKER,
                r=(
                    form_data.r
                    if form_data.r
                    else request.app.state.config.RELEVANCE_THRESHOLD
                ),
                hybrid_bm25_weight=(
                    form_data.hybrid_bm25_weight
                    if form_data.hybrid_bm25_weight
                    else request.app.state.config.HYBRID_BM25_WEIGHT
                ),
                enable_enriched_texts=(
                    form_data.enable_enriched_texts
                    if form_data.enable_enriched_texts is not None
                    else request.app.state.config.ENABLE_RAG_HYBRID_SEARCH_ENRICHED_TEXTS
                ),
            )
        else:
            return await query_collection(
                collection_names=form_data.collection_names,
                queries=[form_data.query],
                embedding_function=lambda query, prefix: request.app.state.EMBEDDING_FUNCTION(
                    query, prefix=prefix, user=user
                ),
                k=form_data.k if form_data.k else request.app.state.config.TOP_K,
            )

    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


####################################
#
# Vector DB operations
#
####################################


class DeleteForm(BaseModel):
    collection_name: str
    file_id: str


@router.post("/delete")
def delete_entries_from_collection(
    form_data: DeleteForm,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    try:
        if VECTOR_DB_CLIENT.has_collection(collection_name=form_data.collection_name):
            file = Files.get_file_by_id(form_data.file_id, db=db)
            if not file:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ERROR_MESSAGES.NOT_FOUND,
                )
            hash = file.hash

            VECTOR_DB_CLIENT.delete(
                collection_name=form_data.collection_name,
                metadata={"hash": hash},
            )
            return {"status": True}
        else:
            return {"status": False}
    except Exception as e:
        log.exception(e)
        return {"status": False}


@router.post("/reset/db")
def reset_vector_db(user=Depends(get_admin_user), db: Session = Depends(get_session)):
    VECTOR_DB_CLIENT.reset()
    Knowledges.delete_all_knowledge(db=db)


@router.post("/reset/uploads")
def reset_upload_dir(user=Depends(get_admin_user)) -> bool:
    folder = f"{UPLOAD_DIR}"
    try:
        # Check if the directory exists
        if os.path.exists(folder):
            # Iterate over all the files and directories in the specified directory
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)  # Remove the file or link
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # Remove the directory
                except Exception as e:
                    log.exception(f"Failed to delete {file_path}. Reason: {e}")
        else:
            log.warning(f"The directory {folder} does not exist")
    except Exception as e:
        log.exception(f"Failed to process the directory {folder}. Reason: {e}")
    return True


if ENV == "dev":

    @router.get("/ef/{text}")
    async def get_embeddings(request: Request, text: Optional[str] = "Hello World!"):
        return {
            "result": await request.app.state.EMBEDDING_FUNCTION(
                text, prefix=RAG_EMBEDDING_QUERY_PREFIX
            )
        }


class BatchProcessFilesForm(BaseModel):
    files: List[FileModel]
    collection_name: str


class BatchProcessFilesResult(BaseModel):
    file_id: str
    status: str
    error: Optional[str] = None


class BatchProcessFilesResponse(BaseModel):
    results: List[BatchProcessFilesResult]
    errors: List[BatchProcessFilesResult]


@router.post("/process/files/batch")
async def process_files_batch(
    request: Request,
    form_data: BatchProcessFilesForm,
    user=Depends(get_verified_user),
) -> BatchProcessFilesResponse:
    """
    Process a batch of files and save them to the vector database.

    NOTE: We intentionally do NOT use Depends(get_session) here.
    The save_docs_to_vector_db() call makes external embedding API calls which
    can take 5-60+ seconds for batch operations. Database operations after
    embedding (Files.update_file_by_id) manage their own short-lived sessions.
    """

    collection_name = form_data.collection_name

    file_results: List[BatchProcessFilesResult] = []
    file_errors: List[BatchProcessFilesResult] = []
    file_updates: List[FileUpdateForm] = []

    # Prepare all documents first
    all_docs: List[Document] = []

    for file in form_data.files:
        try:
            # Ownership check: verify the requesting user owns the file or is an admin
            db_file = Files.get_file_by_id(file.id)
            if not db_file:
                file_errors.append(
                    BatchProcessFilesResult(
                        file_id=file.id,
                        status="failed",
                        error="File not found",
                    )
                )
                continue
            if db_file.user_id != user.id and user.role != "admin":
                file_errors.append(
                    BatchProcessFilesResult(
                        file_id=file.id,
                        status="failed",
                        error="Permission denied: not file owner",
                    )
                )
                continue

            text_content = file.data.get("content", "")
            docs: List[Document] = [
                Document(
                    page_content=text_content.replace("<br/>", "\n"),
                    metadata={
                        **file.meta,
                        "name": file.filename,
                        "created_by": file.user_id,
                        "file_id": file.id,
                        "source": file.filename,
                    },
                )
            ]

            all_docs.extend(docs)

            file_updates.append(
                FileUpdateForm(
                    hash=calculate_sha256_string(text_content),
                    data={"content": text_content},
                )
            )
            file_results.append(
                BatchProcessFilesResult(file_id=file.id, status="prepared")
            )

        except Exception as e:
            log.error(f"process_files_batch: Error processing file {file.id}: {str(e)}")
            file_errors.append(
                BatchProcessFilesResult(file_id=file.id, status="failed", error=str(e))
            )

    # Save all documents in one batch
    if all_docs:
        try:
            await run_in_threadpool(
                save_docs_to_vector_db,
                request,
                all_docs,
                collection_name,
                add=True,
                user=user,
            )

            # Update all files with collection name
            for file_update, file_result in zip(file_updates, file_results):
                Files.update_file_by_id(id=file_result.file_id, form_data=file_update)
                file_result.status = "completed"

        except Exception as e:
            log.error(
                f"process_files_batch: Error saving documents to vector DB: {str(e)}"
            )
            for file_result in file_results:
                file_result.status = "failed"
                file_errors.append(
                    BatchProcessFilesResult(
                        file_id=file_result.file_id, status="failed", error=str(e)
                    )
                )

    return BatchProcessFilesResponse(results=file_results, errors=file_errors)
