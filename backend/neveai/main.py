import asyncio
import inspect
import json
import logging
import mimetypes
import os
import shutil
import sys
import time
import webbrowser
import random
import re
from uuid import uuid4


from contextlib import asynccontextmanager
from urllib.parse import urlencode, parse_qs, urlparse, unquote
from pydantic import BaseModel
from sqlalchemy import text

from typing import Optional
from aiocache import cached
import aiohttp
import anyio.to_thread
import requests
from redis import Redis


from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
    applications,
    BackgroundTasks,
)
from fastapi.openapi.docs import get_swagger_ui_html

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from starlette_compress import CompressMiddleware

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response, StreamingResponse
from starlette.datastructures import Headers

from neveai.utils import logger
from neveai.utils.audit import AuditLevel, AuditLoggingMiddleware
from neveai.utils.logger import start_logger
from neveai.socket.main import (
    MODELS,
    app as socket_app,
    periodic_usage_pool_cleanup,
    periodic_session_pool_cleanup,
    get_event_emitter,
    get_models_in_use,
)
from neveai.routers import (
    audio,
    llamacpp,
    retrieval,
    tasks,
    auths,
    chats,
    folders,
    configs,
    groups,
    files,
    memories,
    models,
    knowledge,
    skills,
    tools,
    users,
    utils,
    terminals,
    stable_diffusion,
    music_generation,
    video_generation,
)

from neveai.routers.retrieval import (
    get_embedding_function,
    get_reranking_function,
    get_ef,
    get_rf,
)


from sqlalchemy.orm import Session
from neveai.internal.db import ScopedSession, engine, get_session

from neveai.models.models import Models
from neveai.models.users import UserModel, Users
from neveai.models.chats import Chats

from neveai.config import (
    # OpenAI
    # Direct Connections
    ENABLE_DIRECT_CONNECTIONS,
    # Model list
    ENABLE_BASE_MODELS_CACHE,
    # Thread pool size for FastAPI/AnyIO
    THREAD_POOL_SIZE,
    # Tool Server Configs
    TOOL_SERVER_CONNECTIONS,
    # Terminal Server
    TERMINAL_SERVER_CONNECTIONS,
    # Code Execution
    ENABLE_CODE_EXECUTION,
    CODE_EXECUTION_ENGINE,
    CODE_EXECUTION_JUPYTER_URL,
    CODE_EXECUTION_JUPYTER_AUTH,
    CODE_EXECUTION_JUPYTER_AUTH_TOKEN,
    CODE_EXECUTION_JUPYTER_AUTH_PASSWORD,
    CODE_EXECUTION_JUPYTER_TIMEOUT,
    ENABLE_CODE_INTERPRETER,
    CODE_INTERPRETER_ENGINE,
    CODE_INTERPRETER_PROMPT_TEMPLATE,
    CODE_INTERPRETER_JUPYTER_URL,
    CODE_INTERPRETER_JUPYTER_AUTH,
    CODE_INTERPRETER_JUPYTER_AUTH_TOKEN,
    CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD,
    CODE_INTERPRETER_JUPYTER_TIMEOUT,
    ENABLE_MEMORIES,
    # Stable Diffusion Local
    ENABLE_STABLE_DIFFUSION,
    ENABLE_MUSIC_GENERATION,
    ENABLE_VIDEO_GENERATION,
    STABLE_DIFFUSION_MODEL,
    STABLE_DIFFUSION_HF_TOKEN,
    STABLE_DIFFUSION_WIDTH,
    STABLE_DIFFUSION_HEIGHT,
    STABLE_DIFFUSION_STEPS,
    STABLE_DIFFUSION_GUIDANCE_SCALE,
    # Audio
    AUDIO_STT_SUPPORTED_CONTENT_TYPES,
    AUDIO_TTS_VOICE,
    AUDIO_TTS_SPLIT_ON,
    WEB_LOADER_CONCURRENT_REQUESTS,
    WEB_LOADER_TIMEOUT,
    WHISPER_MODEL,
    WHISPER_VAD_FILTER,
    WHISPER_LANGUAGE,
    WHISPER_MODEL_AUTO_UPDATE,
    WHISPER_MODEL_DIR,
    # Retrieval
    RAG_TEMPLATE,
    DEFAULT_RAG_TEMPLATE,
    RAG_FULL_CONTEXT,
    BYPASS_EMBEDDING_AND_RETRIEVAL,
    RAG_EMBEDDING_ENGINE,
    RAG_EMBEDDING_MODEL,
    RAG_EMBEDDING_MODEL_AUTO_UPDATE,
    RAG_EMBEDDING_MODEL_TRUST_REMOTE_CODE,
    RAG_RERANKING_MODEL,
    RAG_RERANKING_MODEL_AUTO_UPDATE,
    RAG_RERANKING_MODEL_TRUST_REMOTE_CODE,
    RAG_EMBEDDING_BATCH_SIZE,
    ENABLE_ASYNC_EMBEDDING,
    RAG_EMBEDDING_CONCURRENT_REQUESTS,
    RAG_RERANKING_ENGINE,
    RAG_TOP_K,
    RAG_TOP_K_RERANKER,
    RAG_RELEVANCE_THRESHOLD,
    RAG_HYBRID_BM25_WEIGHT,
    RAG_ALLOWED_FILE_EXTENSIONS,
    RAG_FILE_MAX_COUNT,
    RAG_FILE_MAX_SIZE,
    FILE_IMAGE_COMPRESSION_WIDTH,
    FILE_IMAGE_COMPRESSION_HEIGHT,
    CHUNK_OVERLAP,
    CHUNK_MIN_SIZE_TARGET,
    CHUNK_SIZE,
    RAG_TEXT_SPLITTER,
    ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER,
    TIKTOKEN_ENCODING_NAME,
    PDF_EXTRACT_IMAGES,
    PDF_LOADER_MODE,
    YOUTUBE_LOADER_LANGUAGE,
    YOUTUBE_LOADER_PROXY_URL,
    # Retrieval (Web Search)
    ENABLE_WEB_SEARCH,
    WEB_SEARCH_ENGINE,
    BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL,
    BYPASS_WEB_SEARCH_WEB_LOADER,
    WEB_SEARCH_RESULT_COUNT,
    WEB_SEARCH_CONCURRENT_REQUESTS,
    WEB_SEARCH_TRUST_ENV,
    WEB_SEARCH_DOMAIN_FILTER_LIST,
    SEARXNG_QUERY_URL,
    SEARXNG_LANGUAGE,
    DDGS_BACKEND,
    ENABLE_RAG_HYBRID_SEARCH,
    ENABLE_RAG_HYBRID_SEARCH_ENRICHED_TEXTS,
    ENABLE_RAG_LOCAL_WEB_FETCH,
    ENABLE_WEB_LOADER_SSL_VERIFICATION,
    UPLOAD_DIR,
    # NeveAI
    NEVEAI_NAME,
    NEVEAI_BANNERS,
    JWT_EXPIRES_IN,
    ENABLE_FOLDERS,
    FOLDER_MAX_FILE_COUNT,
    ENABLE_COMMUNITY_SHARING,
    BYPASS_ADMIN_ACCESS_CONTROL,
    USER_PERMISSIONS,
    DEFAULT_GROUP_ID,
    DEFAULT_PROMPT_SUGGESTIONS,
    DEFAULT_MODELS,
    DEFAULT_PINNED_MODELS,
    MODEL_ORDER_LIST,
    DEFAULT_MODEL_METADATA,
    DEFAULT_MODEL_PARAMS,
    # Misc
    ENV,
    CACHE_DIR,
    STATIC_DIR,
    FRONTEND_BUILD_DIR,
    CORS_ALLOW_ORIGIN,
    DEFAULT_LOCALE,
    NEVEAI_URL,
    RESPONSE_WATERMARK,
    # Admin
    ENABLE_ADMIN_CHAT_ACCESS,
    BYPASS_ADMIN_ACCESS_CONTROL,
    ENABLE_ADMIN_EXPORT,
    # Tasks
    TASK_MODEL,
    TASK_MODEL_EXTERNAL,
    ENABLE_TITLE_GENERATION,
    ENABLE_FOLLOW_UP_GENERATION,
    ENABLE_SEARCH_QUERY_GENERATION,
    ENABLE_RETRIEVAL_QUERY_GENERATION,
    ENABLE_AUTOCOMPLETE_GENERATION,
    TITLE_GENERATION_PROMPT_TEMPLATE,
    FOLLOW_UP_GENERATION_PROMPT_TEMPLATE,
    IMAGE_PROMPT_GENERATION_PROMPT_TEMPLATE,
    TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE,
    VOICE_MODE_PROMPT_TEMPLATE,
    QUERY_GENERATION_PROMPT_TEMPLATE,
    AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE,
    AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH,
    AppConfig,
    reset_config,
)
from neveai.env import (
    ENABLE_CUSTOM_MODEL_FALLBACK,
    AUDIT_EXCLUDED_PATHS,
    AUDIT_LOG_LEVEL,
    CHANGELOG,
    REDIS_URL,
    REDIS_CLUSTER,
    REDIS_KEY_PREFIX,
    REDIS_SENTINEL_HOSTS,
    REDIS_SENTINEL_PORT,
    GLOBAL_LOG_LEVEL,
    MAX_BODY_LOG_SIZE,
    SAFE_MODE,
    BASE_DIR,
    VERSION,
    DEPLOYMENT_ID,
    INSTANCE_ID,
    NEVEAI_BUILD_HASH,
    NEVEAI_SECRET_KEY,
    NEVEAI_SESSION_COOKIE_SAME_SITE,
    NEVEAI_SESSION_COOKIE_SECURE,
    NEVEAI_AUTH_SIGNOUT_REDIRECT_URL,
    ENABLE_COMPRESSION_MIDDLEWARE,
    ENABLE_WEBSOCKET_SUPPORT,
    BYPASS_MODEL_ACCESS_CONTROL,
    RESET_CONFIG_ON_START,
    ENABLE_VERSION_UPDATE_CHECK,
    EXTERNAL_PWA_MANIFEST_URL,
    AIOHTTP_CLIENT_SESSION_SSL,
    ENABLE_PUBLIC_ACTIVE_USERS_COUNT,
    ENABLE_EASTER_EGGS,
    LOG_FORMAT,
)


from neveai.utils.models import (
    get_all_models,
    get_all_base_models,
    check_model_access,
    get_filtered_models,
)
from neveai.utils.model_defaults import get_effective_model_params
from neveai.utils.chat import (
    generate_chat_completion as chat_completion_handler,
    chat_completed as chat_completed_handler,
)
from neveai.utils.middleware import (
    build_chat_response_context,
    process_chat_payload,
    process_chat_response,
)
from neveai.utils.tools import set_tool_servers, set_terminal_servers

from neveai.utils.auth import (
    get_http_authorization_cred,
    decode_token,
    get_or_create_no_auth_user,
    get_admin_user,
    get_verified_user,
)
from neveai.utils.plugin import install_tool_dependencies
from neveai.utils.oauth import (
    get_oauth_client_info_with_dynamic_client_registration,
    encrypt_data,
    decrypt_data,
    OAuthClientManager,
    OAuthClientInformationFull,
)
from neveai.utils.security_headers import SecurityHeadersMiddleware
from neveai.utils.redis import get_redis_connection

from neveai.tasks import (
    redis_task_command_listener,
    list_task_ids_by_item_id,
    create_task,
    stop_task,
    list_tasks,
)  # Import from tasks.py

from neveai.utils.redis import get_sentinels_from_env


from neveai.constants import ERROR_MESSAGES

if SAFE_MODE:
    print("SAFE MODE ENABLED")

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except (HTTPException, StarletteHTTPException) as ex:
            if ex.status_code == 404:
                if path.endswith(".js"):
                    # Return 404 for javascript files
                    raise ex
                else:
                    response = await super().get_response("index.html", scope)
            else:
                raise ex
        # Prevent browser from caching HTML pages (e.g. index.html)
        # so that new builds are always served fresh on first load
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        # Hashed assets emitted by Vite under _app/immutable/ never change for a given URL,
        # so cache them aggressively to make subsequent boots near-instant.
        elif "/_app/immutable/" in path or path.startswith("_app/immutable/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# Ensure stdout handles UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Store reference to main event loop for sync->async calls (e.g., embedding generation)
    # This allows sync functions to schedule work on the main loop without blocking health checks
    app.state.main_loop = asyncio.get_running_loop()
    previous_exception_handler = app.state.main_loop.get_exception_handler()

    def handle_event_loop_exception(loop, context):
        exception = context.get("exception")
        handle = str(context.get("handle") or "")
        if (
            isinstance(exception, ConnectionResetError)
            and getattr(exception, "winerror", None) == 10054
            and "_ProactorBasePipeTransport._call_connection_lost" in handle
        ):
            log.debug("Client closed a partial-content connection")
            return
        if previous_exception_handler is not None:
            previous_exception_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    if os.name == "nt":
        app.state.main_loop.set_exception_handler(handle_event_loop_exception)

    app.state.instance_id = INSTANCE_ID
    start_logger()

    if app.state.config.RAG_EMBEDDING_ENGINE == "":
        app.state.embedding_init_task = asyncio.create_task(
            _initialize_local_embedding_model(app)
        )

    if RESET_CONFIG_ON_START:
        reset_config()

    async def install_tool_dependencies_background():
        log.info("Installing external dependencies of functions and tools...")
        try:
            await asyncio.to_thread(install_tool_dependencies)
        except Exception as e:
            log.warning(f"Failed to install function/tool dependencies in background: {e}")

    app.state.tool_dependency_install_task = asyncio.create_task(
        install_tool_dependencies_background()
    )

    app.state.redis = get_redis_connection(
        redis_url=REDIS_URL,
        redis_sentinels=get_sentinels_from_env(
            REDIS_SENTINEL_HOSTS, REDIS_SENTINEL_PORT
        ),
        redis_cluster=REDIS_CLUSTER,
        async_mode=True,
    )

    if app.state.redis is not None:
        app.state.redis_task_command_listener = asyncio.create_task(
            redis_task_command_listener(app)
        )

    if THREAD_POOL_SIZE and THREAD_POOL_SIZE > 0:
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = THREAD_POOL_SIZE

    asyncio.create_task(periodic_usage_pool_cleanup())
    asyncio.create_task(periodic_session_pool_cleanup())

    if app.state.config.ENABLE_BASE_MODELS_CACHE:
        try:
            await get_all_models(
                Request(
                    # Creating a mock request object to pass to get_all_models
                    {
                        "type": "http",
                        "asgi.version": "3.0",
                        "asgi.spec_version": "2.0",
                        "method": "GET",
                        "path": "/internal",
                        "query_string": b"",
                        "headers": Headers({}).raw,
                        "client": ("127.0.0.1", 12345),
                        "server": ("127.0.0.1", 80),
                        "scheme": "http",
                        "app": app,
                    }
                ),
                None,
            )
        except Exception as e:
            log.warning(f"Failed to pre-fetch models at startup: {e}")

    # Pre-fetch tool server specs so the first request doesn't pay the latency cost
    if len(app.state.config.TOOL_SERVER_CONNECTIONS) > 0:
        log.info("Initializing tool servers...")
        try:
            mock_request = Request(
                {
                    "type": "http",
                    "asgi.version": "3.0",
                    "asgi.spec_version": "2.0",
                    "method": "GET",
                    "path": "/internal",
                    "query_string": b"",
                    "headers": Headers({}).raw,
                    "client": ("127.0.0.1", 12345),
                    "server": ("127.0.0.1", 80),
                    "scheme": "http",
                    "app": app,
                }
            )
            await set_tool_servers(mock_request)
            log.info(f"Initialized {len(app.state.TOOL_SERVERS)} tool server(s)")

            await set_terminal_servers(mock_request)
            log.info(
                f"Initialized {len(app.state.TERMINAL_SERVERS)} terminal server(s)"
            )
        except Exception as e:
            log.warning(f"Failed to initialize tool/terminal servers at startup: {e}")

    yield

    if os.name == "nt":
        app.state.main_loop.set_exception_handler(previous_exception_handler)

    if hasattr(app.state, "redis_task_command_listener"):
        app.state.redis_task_command_listener.cancel()


app = FastAPI(
    title="Neve",
    docs_url="/docs" if ENV == "dev" else None,
    openapi_url="/openapi.json" if ENV == "dev" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# For Integrations
oauth_client_manager = OAuthClientManager(app)
app.state.oauth_client_manager = oauth_client_manager

app.state.instance_id = None
app.state.config = AppConfig(
    redis_url=REDIS_URL,
    redis_sentinels=get_sentinels_from_env(REDIS_SENTINEL_HOSTS, REDIS_SENTINEL_PORT),
    redis_cluster=REDIS_CLUSTER,
    redis_key_prefix=REDIS_KEY_PREFIX,
)
app.state.redis = None

app.state.NEVEAI_NAME = NEVEAI_NAME
app.state.LICENSE_METADATA = None



########################################
#
# OPENAI
#
########################################


app.state.OPENAI_MODELS = {}

########################################
#
# TOOL SERVERS
#
########################################

app.state.config.TOOL_SERVER_CONNECTIONS = TOOL_SERVER_CONNECTIONS
app.state.TOOL_SERVERS = []

########################################
#
# TERMINAL SERVER
#
########################################

app.state.config.TERMINAL_SERVER_CONNECTIONS = TERMINAL_SERVER_CONNECTIONS
app.state.TERMINAL_SERVERS = []

########################################
#
# DIRECT CONNECTIONS
#
########################################

app.state.config.ENABLE_DIRECT_CONNECTIONS = ENABLE_DIRECT_CONNECTIONS
app.state.config.ENABLE_DIRECT_CONNECTIONS = False

########################################
#
# MODELS
#
########################################

app.state.config.ENABLE_BASE_MODELS_CACHE = ENABLE_BASE_MODELS_CACHE
app.state.BASE_MODELS = []

########################################
#
# NEVEAI
#
########################################

app.state.config.NEVEAI_URL = NEVEAI_URL
app.state.config.JWT_EXPIRES_IN = JWT_EXPIRES_IN


app.state.config.DEFAULT_MODELS = DEFAULT_MODELS
app.state.config.DEFAULT_PINNED_MODELS = DEFAULT_PINNED_MODELS
app.state.config.MODEL_ORDER_LIST = MODEL_ORDER_LIST
app.state.config.DEFAULT_MODEL_METADATA = DEFAULT_MODEL_METADATA
app.state.config.DEFAULT_MODEL_PARAMS = DEFAULT_MODEL_PARAMS


app.state.config.DEFAULT_PROMPT_SUGGESTIONS = DEFAULT_PROMPT_SUGGESTIONS
app.state.config.DEFAULT_GROUP_ID = DEFAULT_GROUP_ID

app.state.config.RESPONSE_WATERMARK = RESPONSE_WATERMARK

app.state.config.USER_PERMISSIONS = USER_PERMISSIONS
app.state.config.BANNERS = NEVEAI_BANNERS


app.state.config.ENABLE_FOLDERS = ENABLE_FOLDERS
app.state.config.FOLDER_MAX_FILE_COUNT = FOLDER_MAX_FILE_COUNT
app.state.config.ENABLE_COMMUNITY_SHARING = ENABLE_COMMUNITY_SHARING

# Migrate legacy access_control â†’ access_grants on boot
from neveai.utils.access_control import migrate_access_control

connections = app.state.config.TOOL_SERVER_CONNECTIONS
if any("access_control" in c.get("config", {}) for c in connections):
    for connection in connections:
        migrate_access_control(connection.get("config", {}))
    app.state.config.TOOL_SERVER_CONNECTIONS = connections



app.state.NEVEAI_AUTH_SIGNOUT_REDIRECT_URL = NEVEAI_AUTH_SIGNOUT_REDIRECT_URL
app.state.EXTERNAL_PWA_MANIFEST_URL = EXTERNAL_PWA_MANIFEST_URL

app.state.USER_COUNT = None

app.state.TOOLS = {}
app.state.TOOL_CONTENTS = {}

########################################
#
# RETRIEVAL
#
########################################


app.state.config.TOP_K = RAG_TOP_K
app.state.config.TOP_K_RERANKER = RAG_TOP_K_RERANKER
app.state.config.RELEVANCE_THRESHOLD = RAG_RELEVANCE_THRESHOLD
app.state.config.HYBRID_BM25_WEIGHT = RAG_HYBRID_BM25_WEIGHT


app.state.config.ALLOWED_FILE_EXTENSIONS = RAG_ALLOWED_FILE_EXTENSIONS
app.state.config.FILE_MAX_SIZE = RAG_FILE_MAX_SIZE
app.state.config.FILE_MAX_COUNT = RAG_FILE_MAX_COUNT
app.state.config.FILE_IMAGE_COMPRESSION_WIDTH = FILE_IMAGE_COMPRESSION_WIDTH
app.state.config.FILE_IMAGE_COMPRESSION_HEIGHT = FILE_IMAGE_COMPRESSION_HEIGHT


app.state.config.RAG_FULL_CONTEXT = RAG_FULL_CONTEXT
app.state.config.BYPASS_EMBEDDING_AND_RETRIEVAL = BYPASS_EMBEDDING_AND_RETRIEVAL
app.state.config.ENABLE_RAG_HYBRID_SEARCH = ENABLE_RAG_HYBRID_SEARCH
app.state.config.ENABLE_RAG_HYBRID_SEARCH_ENRICHED_TEXTS = (
    ENABLE_RAG_HYBRID_SEARCH_ENRICHED_TEXTS
)
app.state.config.ENABLE_WEB_LOADER_SSL_VERIFICATION = ENABLE_WEB_LOADER_SSL_VERIFICATION

app.state.config.TEXT_SPLITTER = RAG_TEXT_SPLITTER
app.state.config.ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER = (
    ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER
)

app.state.config.TIKTOKEN_ENCODING_NAME = TIKTOKEN_ENCODING_NAME

app.state.config.CHUNK_SIZE = CHUNK_SIZE
app.state.config.CHUNK_MIN_SIZE_TARGET = CHUNK_MIN_SIZE_TARGET
app.state.config.CHUNK_OVERLAP = CHUNK_OVERLAP


app.state.config.RAG_EMBEDDING_ENGINE = RAG_EMBEDDING_ENGINE
app.state.config.RAG_EMBEDDING_ENGINE = ""
app.state.config.RAG_EMBEDDING_MODEL = RAG_EMBEDDING_MODEL
app.state.config.RAG_EMBEDDING_BATCH_SIZE = RAG_EMBEDDING_BATCH_SIZE
app.state.config.ENABLE_ASYNC_EMBEDDING = ENABLE_ASYNC_EMBEDDING
app.state.config.RAG_EMBEDDING_CONCURRENT_REQUESTS = RAG_EMBEDDING_CONCURRENT_REQUESTS

app.state.config.RAG_RERANKING_ENGINE = RAG_RERANKING_ENGINE
app.state.config.RAG_RERANKING_ENGINE = ""
app.state.config.RAG_RERANKING_MODEL = RAG_RERANKING_MODEL

app.state.config.RAG_TEMPLATE = RAG_TEMPLATE

app.state.config.PDF_EXTRACT_IMAGES = PDF_EXTRACT_IMAGES
app.state.config.PDF_LOADER_MODE = PDF_LOADER_MODE

app.state.config.YOUTUBE_LOADER_LANGUAGE = YOUTUBE_LOADER_LANGUAGE
app.state.config.YOUTUBE_LOADER_PROXY_URL = YOUTUBE_LOADER_PROXY_URL


app.state.config.ENABLE_WEB_SEARCH = ENABLE_WEB_SEARCH
app.state.config.ENABLE_WEB_SEARCH = True  # Force-enabled for NeveAI
app.state.config.WEB_SEARCH_ENGINE = WEB_SEARCH_ENGINE
app.state.config.WEB_SEARCH_ENGINE = "searxng"  # Force free SearXNG with DDGS fallback
app.state.config.WEB_SEARCH_DOMAIN_FILTER_LIST = WEB_SEARCH_DOMAIN_FILTER_LIST
app.state.config.WEB_SEARCH_RESULT_COUNT = WEB_SEARCH_RESULT_COUNT
app.state.config.WEB_SEARCH_CONCURRENT_REQUESTS = WEB_SEARCH_CONCURRENT_REQUESTS

app.state.config.WEB_LOADER_CONCURRENT_REQUESTS = WEB_LOADER_CONCURRENT_REQUESTS
app.state.config.WEB_LOADER_TIMEOUT = WEB_LOADER_TIMEOUT

app.state.config.WEB_SEARCH_TRUST_ENV = WEB_SEARCH_TRUST_ENV
app.state.config.BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = (
    BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL
)
app.state.config.BYPASS_WEB_SEARCH_WEB_LOADER = BYPASS_WEB_SEARCH_WEB_LOADER

app.state.config.SEARXNG_QUERY_URL = SEARXNG_QUERY_URL
app.state.config.SEARXNG_LANGUAGE = SEARXNG_LANGUAGE
app.state.config.DDGS_BACKEND = DDGS_BACKEND

app.state.EMBEDDING_FUNCTION = None
app.state.RERANKING_FUNCTION = None
app.state.ef = None
app.state.rf = None
app.state.embedding_init_task = None

app.state.YOUTUBE_LOADER_TRANSLATION = None


def _build_embedding_function(app: FastAPI, embedding_function=None):
    return get_embedding_function(
        embedding_function=embedding_function,
        embedding_batch_size=app.state.config.RAG_EMBEDDING_BATCH_SIZE,
    )


async def _deferred_embedding_function(query, prefix=None, user=None):
    task = app.state.embedding_init_task
    if task is None or (
        task.done()
        and app.state.EMBEDDING_FUNCTION is _deferred_embedding_function
    ):
        task = asyncio.create_task(_initialize_local_embedding_model(app))
        app.state.embedding_init_task = task
    await asyncio.shield(task)
    embedding_function = app.state.EMBEDDING_FUNCTION
    if embedding_function is _deferred_embedding_function:
        raise RuntimeError("O modelo local de embeddings nao pode ser carregado")
    return await embedding_function(query, prefix=prefix, user=user)


async def _initialize_local_embedding_model(app: FastAPI):
    engine = app.state.config.RAG_EMBEDDING_ENGINE
    model = app.state.config.RAG_EMBEDDING_MODEL
    if engine != "":
        return
    try:
        embedding_model = await asyncio.to_thread(get_ef, engine, model)
        if model and embedding_model is None:
            raise RuntimeError(f"Nao foi possivel carregar o modelo de embeddings {model}")
        if (
            app.state.config.RAG_EMBEDDING_ENGINE == engine
            and app.state.config.RAG_EMBEDDING_MODEL == model
            and app.state.EMBEDDING_FUNCTION is _deferred_embedding_function
        ):
            app.state.ef = embedding_model
            app.state.EMBEDDING_FUNCTION = _build_embedding_function(
                app, embedding_function=embedding_model
            )
            log.info("Modelo local de embeddings pronto em segundo plano")
    except Exception as e:
        log.error("Falha ao carregar o modelo local de embeddings: %s", e)


if app.state.config.RAG_EMBEDDING_ENGINE == "":
    app.state.EMBEDDING_FUNCTION = _deferred_embedding_function
else:
    app.state.EMBEDDING_FUNCTION = _build_embedding_function(app)


try:
    if (
        app.state.config.ENABLE_RAG_HYBRID_SEARCH
        and not app.state.config.BYPASS_EMBEDDING_AND_RETRIEVAL
    ):
        app.state.rf = get_rf(
            app.state.config.RAG_RERANKING_MODEL,
        )
except Exception as e:
    log.error("Error updating reranking model: %s", e)

app.state.RERANKING_FUNCTION = get_reranking_function(
    reranking_function=app.state.rf,
)

########################################
#
# CODE EXECUTION
#
########################################

app.state.config.ENABLE_CODE_EXECUTION = ENABLE_CODE_EXECUTION
app.state.config.CODE_EXECUTION_ENGINE = CODE_EXECUTION_ENGINE
app.state.config.CODE_EXECUTION_JUPYTER_URL = CODE_EXECUTION_JUPYTER_URL
app.state.config.CODE_EXECUTION_JUPYTER_AUTH = CODE_EXECUTION_JUPYTER_AUTH
app.state.config.CODE_EXECUTION_JUPYTER_AUTH_TOKEN = CODE_EXECUTION_JUPYTER_AUTH_TOKEN
app.state.config.CODE_EXECUTION_JUPYTER_AUTH_PASSWORD = (
    CODE_EXECUTION_JUPYTER_AUTH_PASSWORD
)
app.state.config.CODE_EXECUTION_JUPYTER_TIMEOUT = CODE_EXECUTION_JUPYTER_TIMEOUT

app.state.config.ENABLE_CODE_INTERPRETER = ENABLE_CODE_INTERPRETER
app.state.config.CODE_INTERPRETER_ENGINE = CODE_INTERPRETER_ENGINE
app.state.config.CODE_INTERPRETER_PROMPT_TEMPLATE = CODE_INTERPRETER_PROMPT_TEMPLATE

app.state.config.CODE_INTERPRETER_JUPYTER_URL = CODE_INTERPRETER_JUPYTER_URL
app.state.config.CODE_INTERPRETER_JUPYTER_AUTH = CODE_INTERPRETER_JUPYTER_AUTH
app.state.config.CODE_INTERPRETER_JUPYTER_AUTH_TOKEN = (
    CODE_INTERPRETER_JUPYTER_AUTH_TOKEN
)
app.state.config.CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD = (
    CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD
)
app.state.config.CODE_INTERPRETER_JUPYTER_TIMEOUT = CODE_INTERPRETER_JUPYTER_TIMEOUT

app.state.config.ENABLE_MEMORIES = ENABLE_MEMORIES


########################################
#
# STABLE DIFFUSION LOCAL
#
########################################

app.state.config.ENABLE_STABLE_DIFFUSION = ENABLE_STABLE_DIFFUSION
app.state.config.ENABLE_MUSIC_GENERATION = ENABLE_MUSIC_GENERATION
app.state.config.ENABLE_VIDEO_GENERATION = ENABLE_VIDEO_GENERATION
app.state.config.STABLE_DIFFUSION_MODEL = STABLE_DIFFUSION_MODEL
app.state.config.STABLE_DIFFUSION_HF_TOKEN = STABLE_DIFFUSION_HF_TOKEN
app.state.config.STABLE_DIFFUSION_WIDTH = STABLE_DIFFUSION_WIDTH
app.state.config.STABLE_DIFFUSION_HEIGHT = STABLE_DIFFUSION_HEIGHT
app.state.config.STABLE_DIFFUSION_STEPS = STABLE_DIFFUSION_STEPS
app.state.config.STABLE_DIFFUSION_GUIDANCE_SCALE = STABLE_DIFFUSION_GUIDANCE_SCALE


########################################
#
# AUDIO
#
########################################

app.state.config.STT_SUPPORTED_CONTENT_TYPES = AUDIO_STT_SUPPORTED_CONTENT_TYPES
app.state.config.WHISPER_MODEL = WHISPER_MODEL
app.state.config.TTS_VOICE = AUDIO_TTS_VOICE
app.state.config.TTS_SPLIT_ON = AUDIO_TTS_SPLIT_ON


app.state.faster_whisper_model = None


########################################
#
# TASKS
#
########################################


app.state.config.TASK_MODEL = TASK_MODEL
app.state.config.TASK_MODEL_EXTERNAL = TASK_MODEL_EXTERNAL


app.state.config.ENABLE_SEARCH_QUERY_GENERATION = ENABLE_SEARCH_QUERY_GENERATION
app.state.config.ENABLE_RETRIEVAL_QUERY_GENERATION = ENABLE_RETRIEVAL_QUERY_GENERATION
app.state.config.ENABLE_AUTOCOMPLETE_GENERATION = ENABLE_AUTOCOMPLETE_GENERATION
app.state.config.ENABLE_TITLE_GENERATION = ENABLE_TITLE_GENERATION
app.state.config.ENABLE_FOLLOW_UP_GENERATION = ENABLE_FOLLOW_UP_GENERATION


app.state.config.TITLE_GENERATION_PROMPT_TEMPLATE = TITLE_GENERATION_PROMPT_TEMPLATE
app.state.config.IMAGE_PROMPT_GENERATION_PROMPT_TEMPLATE = (
    IMAGE_PROMPT_GENERATION_PROMPT_TEMPLATE
)
app.state.config.FOLLOW_UP_GENERATION_PROMPT_TEMPLATE = (
    FOLLOW_UP_GENERATION_PROMPT_TEMPLATE
)

app.state.config.TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE = (
    TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE
)
app.state.config.QUERY_GENERATION_PROMPT_TEMPLATE = QUERY_GENERATION_PROMPT_TEMPLATE
app.state.config.AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE = (
    AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE
)
app.state.config.AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH = (
    AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH
)
app.state.config.VOICE_MODE_PROMPT_TEMPLATE = VOICE_MODE_PROMPT_TEMPLATE


########################################
#
# NEVEAI
#
########################################

app.state.MODELS = MODELS

# Add the middleware to the app
if ENABLE_COMPRESSION_MIDDLEWARE:
    app.add_middleware(CompressMiddleware)


class RedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Check if the request is a GET request
        if request.method == "GET":
            path = request.url.path
            query_params = dict(parse_qs(urlparse(str(request.url)).query))

            redirect_params = {}

            # Check for the specific watch path and the presence of 'v' parameter
            if path.endswith("/watch") and "v" in query_params:
                # Extract the first 'v' parameter
                youtube_video_id = query_params["v"][0]
                redirect_params["youtube"] = youtube_video_id

            if "shared" in query_params and len(query_params["shared"]) > 0:
                # PWA share_target support

                text = query_params["shared"][0]
                if text:
                    urls = re.match(r"https://\S+", text)
                    if urls:
                        from neveai.retrieval.loaders.youtube import _parse_video_id

                        if youtube_video_id := _parse_video_id(urls[0]):
                            redirect_params["youtube"] = youtube_video_id
                        else:
                            redirect_params["load-url"] = urls[0]
                    else:
                        redirect_params["q"] = text

            if redirect_params:
                redirect_url = f"/?{urlencode(redirect_params)}"
                return RedirectResponse(url=redirect_url)

        # Proceed with the normal flow of other requests
        response = await call_next(request)
        return response


app.add_middleware(RedirectMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


@app.middleware("http")
async def commit_session_after_request(request: Request, call_next):
    response = await call_next(request)
    # log.debug("Commit session after request")
    try:
        ScopedSession.commit()
    finally:
        # CRITICAL: remove() returns the connection to the pool.
        # Without this, connections remain "checked out" and accumulate
        # as "idle in transaction" in PostgreSQL.
        ScopedSession.remove()
    return response


@app.middleware("http")
async def check_url(request: Request, call_next):
    start_time = int(time.time())
    request.state.token = get_http_authorization_cred(
        request.headers.get("Authorization")
    )
    # Fallback to cookie token for browser sessions
    if request.state.token is None and request.cookies.get("token"):
        from fastapi.security import HTTPAuthorizationCredentials

        request.state.token = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=request.cookies.get("token")
        )

    response = await call_next(request)
    process_time = int(time.time()) - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.middleware("http")
async def inspect_websocket(request: Request, call_next):
    if (
        "/ws/socket.io" in request.url.path
        and request.query_params.get("transport") == "websocket"
    ):
        upgrade = (request.headers.get("Upgrade") or "").lower()
        connection = (request.headers.get("Connection") or "").lower().split(",")
        # Check that there's the correct headers for an upgrade, else reject the connection
        # This is to work around this upstream issue: https://github.com/miguelgrinberg/python-engineio/issues/367
        if upgrade != "websocket" or "upgrade" not in connection:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid WebSocket upgrade request"},
            )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGIN,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/ws", socket_app)


app.include_router(llamacpp.router, prefix="/llamacpp", tags=["llamacpp"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(stable_diffusion.router, prefix="/api/v1/stable-diffusion", tags=["stable-diffusion"])
app.include_router(music_generation.router, prefix="/api/v1/music-generation", tags=["music-generation"])
app.include_router(video_generation.router, prefix="/api/v1/video-generation", tags=["video-generation"])

app.include_router(audio.router, prefix="/api/v1/audio", tags=["audio"])
app.include_router(retrieval.router, prefix="/api/v1/retrieval", tags=["retrieval"])

app.include_router(configs.router, prefix="/api/v1/configs", tags=["configs"])

app.include_router(auths.router, prefix="/api/v1/auths", tags=["auths"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])


app.include_router(chats.router, prefix="/api/v1/chats", tags=["chats"])


app.include_router(models.router, prefix="/api/v1/models", tags=["models"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(tools.router, prefix="/api/v1/tools", tags=["tools"])
app.include_router(skills.router, prefix="/api/v1/skills", tags=["skills"])

app.include_router(memories.router, prefix="/api/v1/memories", tags=["memories"])
app.include_router(folders.router, prefix="/api/v1/folders", tags=["folders"])
app.include_router(groups.router, prefix="/api/v1/groups", tags=["groups"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(utils.router, prefix="/api/v1/utils", tags=["utils"])
app.include_router(terminals.router, prefix="/api/v1/terminals", tags=["terminals"])

try:
    audit_level = AuditLevel(AUDIT_LOG_LEVEL)
except ValueError as e:
    logger.error(f"Invalid audit level: {AUDIT_LOG_LEVEL}. Error: {e}")
    audit_level = AuditLevel.NONE

if audit_level != AuditLevel.NONE:
    app.add_middleware(
        AuditLoggingMiddleware,
        audit_level=audit_level,
        excluded_paths=AUDIT_EXCLUDED_PATHS,
        max_body_size=MAX_BODY_LOG_SIZE,
    )
##################################
#
# Chat Endpoints
#
##################################


@app.get("/api/models")
@app.get("/api/v1/models")  # Experimental: Compatibility with OpenAI API
async def get_models(
    request: Request, refresh: bool = False, user=Depends(get_verified_user)
):
    all_models = await get_all_models(request, refresh=refresh, user=user)

    models = []
    for model in all_models:
        # Filter out filter pipelines
        if "pipeline" in model and model["pipeline"].get("type", None) == "filter":
            continue

        # Filter out arena / evaluation models from the user-facing list
        if model.get("owned_by") == "arena":
            continue

        # Remove profile image URL to reduce payload size
        if model.get("info", {}).get("meta", {}).get("profile_image_url"):
            model["info"]["meta"].pop("profile_image_url", None)

        try:
            model_tags = [
                tag.get("name")
                for tag in model.get("info", {}).get("meta", {}).get("tags", [])
            ]
            tags = [tag.get("name") for tag in model.get("tags", [])]

            tags = list(set(model_tags + tags))
            model["tags"] = [{"name": tag} for tag in tags]
        except Exception as e:
            log.debug(f"Error processing model tags: {e}")
            model["tags"] = []
            pass

        models.append(model)

    model_order_list = request.app.state.config.MODEL_ORDER_LIST
    if model_order_list:
        model_order_dict = {model_id: i for i, model_id in enumerate(model_order_list)}
        # Sort models by order list priority, with fallback for those not in the list
        models.sort(
            key=lambda model: (
                model_order_dict.get(model.get("id", ""), float("inf")),
                (model.get("name", "") or ""),
            )
        )

    models = get_filtered_models(models, user)

    log.debug(
        f"/api/models returned filtered models accessible to the user: {json.dumps([model.get('id') for model in models])}"
    )
    return {"data": models}


@app.get("/api/models/base")
async def get_base_models(request: Request, user=Depends(get_admin_user)):
    models = await get_all_base_models(request, user=user)
    return {"data": models}


@app.post("/api/chat/completions")
@app.post("/api/v1/chat/completions")  # Experimental: Compatibility with OpenAI API
async def chat_completion(
    request: Request,
    form_data: dict,
    user=Depends(get_verified_user),
):
    if not request.app.state.MODELS:
        await get_all_models(request, user=user)

    model_id = form_data.get("model", None)
    model_item = form_data.pop("model_item", {})
    tasks = form_data.pop("background_tasks", None)

    metadata = {}
    try:
        model_info = None
        if not model_item.get("direct", False):
            if model_id not in request.app.state.MODELS:
                raise Exception("Model not found")

            model = request.app.state.MODELS[model_id]
            model_info = Models.get_model_by_id(model_id)

            # Check if user has access to the model
            if not BYPASS_MODEL_ACCESS_CONTROL and (
                user.role != "admin" or not BYPASS_ADMIN_ACCESS_CONTROL
            ):
                try:
                    check_model_access(user, model)
                except Exception as e:
                    raise e
        else:
            model = model_item

            request.state.direct = True
            request.state.model = model

        # Model params: global defaults as base, per-model overrides win
        default_model_params = (
            getattr(request.app.state.config, "DEFAULT_MODEL_PARAMS", None) or {}
        )
        model_info_params = get_effective_model_params(model_info, default_model_params)

        # Check base model existence for custom models
        if model_info and model_info.base_model_id:
            base_model_id = model_info.base_model_id
            if base_model_id not in request.app.state.MODELS:
                if ENABLE_CUSTOM_MODEL_FALLBACK:
                    default_models = (
                        request.app.state.config.DEFAULT_MODELS or ""
                    ).split(",")

                    fallback_model_id = (
                        default_models[0].strip() if default_models[0] else None
                    )

                    if (
                        fallback_model_id
                        and fallback_model_id in request.app.state.MODELS
                    ):
                        # Update model and form_data so routing uses the fallback model's type
                        model = request.app.state.MODELS[fallback_model_id]
                        form_data["model"] = fallback_model_id
                    else:
                        raise Exception("Model not found")
                else:
                    raise Exception("Model not found")

        # Chat Params
        stream_delta_chunk_size = form_data.get("params", {}).get(
            "stream_delta_chunk_size"
        )
        reasoning_tags = form_data.get("params", {}).get("reasoning_tags")

        # Model Params
        if (
            "stream" not in form_data
            and model_info_params.get("stream_response") is not None
        ):
            form_data["stream"] = model_info_params.get("stream_response")

        if model_info_params.get("stream_delta_chunk_size"):
            stream_delta_chunk_size = model_info_params.get("stream_delta_chunk_size")

        if model_info_params.get("reasoning_tags") is not None:
            reasoning_tags = model_info_params.get("reasoning_tags")

        metadata = {
            "user_id": user.id,
            "chat_id": form_data.pop("chat_id", None),
            "message_id": form_data.pop("id", None),
            "parent_message": form_data.pop("parent_message", None),
            "parent_message_id": form_data.pop("parent_id", None),
            "session_id": form_data.pop("session_id", None),
            "tool_ids": form_data.get("tool_ids", None),
            "tool_servers": form_data.pop("tool_servers", None),
            "files": form_data.get("files", None),
            "features": form_data.get("features", {}),
            "variables": form_data.get("variables", {}),
            "model": model,
            "direct": model_item.get("direct", False),
            "params": {
                "stream_delta_chunk_size": stream_delta_chunk_size,
                "reasoning_tags": reasoning_tags,
                "function_calling": (
                    "native"
                    if (
                        form_data.get("params", {}).get("function_calling") == "native"
                        or model_info_params.get("function_calling") == "native"
                    )
                    else "default"
                ),
            },
        }

        if metadata.get("chat_id") and user:
            if not metadata["chat_id"].startswith(
                "local:"
            ):  # temporary chats are not stored

                # Verify chat ownership â€” lightweight EXISTS check avoids
                # deserializing the full chat JSON blob just to confirm the row exists
                if (
                    not Chats.is_chat_owner(metadata["chat_id"], user.id)
                    and user.role != "admin"
                ):  # admins can access any chat
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=ERROR_MESSAGES.DEFAULT(),
                    )

                # Insert chat files from parent message if any
                parent_message = metadata.get("parent_message") or {}
                parent_message_files = parent_message.get("files", [])
                if parent_message_files:
                    try:
                        Chats.insert_chat_files(
                            metadata["chat_id"],
                            parent_message.get("id"),
                            [
                                file_item.get("id")
                                for file_item in parent_message_files
                                if file_item.get("type") == "file"
                            ],
                            user.id,
                        )
                    except Exception as e:
                        log.debug(f"Error inserting chat files: {e}")
                        pass

        request.state.metadata = metadata
        form_data["metadata"] = metadata

    except Exception as e:
        log.debug(f"Error processing chat metadata: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    async def process_chat(request, form_data, user, metadata, model):
        try:
            form_data, metadata, events = await process_chat_payload(
                request, form_data, user, metadata, model
            )

            # If a handler already emitted the full response (e.g. Stable Diffusion),
            # skip the LLM call entirely.
            if metadata.get("skip_llm"):
                return

            response = await chat_completion_handler(request, form_data, user)
            if metadata.get("chat_id") and metadata.get("message_id"):
                try:
                    if not metadata["chat_id"].startswith("local:"):
                        Chats.upsert_message_to_chat_by_id_and_message_id(
                            metadata["chat_id"],
                            metadata["message_id"],
                            {
                                "parentId": metadata.get("parent_message_id", None),
                                "model": model_id,
                            },
                        )
                except Exception:
                    pass

            ctx = build_chat_response_context(
                request, form_data, user, model, metadata, tasks, events
            )

            return await process_chat_response(response, ctx)
        except asyncio.CancelledError:
            log.info("Chat processing was cancelled")
            try:
                event_emitter = get_event_emitter(metadata)
                await asyncio.shield(
                    event_emitter(
                        {"type": "chat:tasks:cancel"},
                    )
                )
            except Exception as e:
                pass
            finally:
                raise  # re-raise to ensure proper task cancellation handling
        except Exception as e:
            log.exception(f"Error processing chat payload: {e}")
            if metadata.get("chat_id") and metadata.get("message_id"):
                # Update the chat message with the error
                if not metadata["chat_id"].startswith("local:"):
                    try:
                        Chats.upsert_message_to_chat_by_id_and_message_id(
                            metadata["chat_id"],
                            metadata["message_id"],
                            {
                                "parentId": metadata.get("parent_message_id", None),
                                "error": {"content": str(e)},
                            },
                        )
                    except Exception as db_error:
                        log.debug(f"Error saving chat failure: {db_error}")

                try:
                    event_emitter = get_event_emitter(metadata)
                    await event_emitter(
                        {
                            "type": "chat:message:error",
                            "data": {"error": {"content": str(e)}},
                        }
                    )
                    await event_emitter(
                        {"type": "chat:tasks:cancel"},
                    )
                except Exception as emit_error:
                    log.debug(f"Error emitting chat failure: {emit_error}")
        finally:
            try:
                if mcp_clients := metadata.get("mcp_clients"):
                    for client in reversed(mcp_clients.values()):
                        await client.disconnect()
            except Exception as e:
                log.debug(f"Error cleaning up: {e}")
                pass
            # Emit chat:active=false when task completes
            try:
                if metadata.get("chat_id"):
                    event_emitter = get_event_emitter(metadata, update_db=False)
                    if event_emitter:
                        await event_emitter(
                            {"type": "chat:active", "data": {"active": False}}
                        )
            except Exception as e:
                log.debug(f"Error emitting chat:active: {e}")

    if (
        metadata.get("session_id")
        and metadata.get("chat_id")
        and metadata.get("message_id")
    ):
        # Asynchronous Chat Processing
        task_id, _ = await create_task(
            request.app.state.redis,
            process_chat(request, form_data, user, metadata, model),
            id=metadata["chat_id"],
        )
        # Emit chat:active=true when task starts
        event_emitter = get_event_emitter(metadata, update_db=False)
        if event_emitter:
            await event_emitter({"type": "chat:active", "data": {"active": True}})
        return {"status": True, "task_id": task_id}
    else:
        return await process_chat(request, form_data, user, metadata, model)


# Alias for chat_completion (Legacy)
generate_chat_completions = chat_completion
generate_chat_completion = chat_completion


@app.post("/api/chat/completed")
async def chat_completed(
    request: Request, form_data: dict, user=Depends(get_verified_user)
):
    try:
        model_item = form_data.pop("model_item", {})

        if model_item.get("direct", False):
            request.state.direct = True
            request.state.model = model_item

        return await chat_completed_handler(request, form_data, user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/api/tasks/stop/{task_id}")
async def stop_task_endpoint(
    request: Request, task_id: str, user=Depends(get_verified_user)
):
    try:
        result = await stop_task(request.app.state.redis, task_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/api/tasks")
async def list_tasks_endpoint(request: Request, user=Depends(get_verified_user)):
    return {"tasks": await list_tasks(request.app.state.redis)}


@app.get("/api/tasks/chat/{chat_id}")
async def list_tasks_by_chat_id_endpoint(
    request: Request, chat_id: str, user=Depends(get_verified_user)
):
    chat = Chats.get_chat_by_id(chat_id)
    if chat is None or chat.user_id != user.id:
        return {"task_ids": []}

    task_ids = await list_task_ids_by_item_id(request.app.state.redis, chat_id)

    log.debug(f"Task IDs for chat {chat_id}: {task_ids}")
    return {"task_ids": task_ids}


##################################
#
# Config Endpoints
#
##################################


@app.get("/api/config")
async def get_app_config(request: Request):
    user = None
    token = None

    auth_header = request.headers.get("Authorization")
    if auth_header:
        cred = get_http_authorization_cred(auth_header)
        if cred:
            token = cred.credentials

    if not token and "token" in request.cookies:
        token = request.cookies.get("token")

    if token:
        data = decode_token(token)
        if data is not None and "id" in data:
            user = Users.get_user_by_id(data["id"])

    if user is None:
        user = get_or_create_no_auth_user()

    user_count = Users.get_num_users()
    return {
        "status": True,
        "name": app.state.NEVEAI_NAME,
        "version": VERSION,
        "default_locale": str(DEFAULT_LOCALE),
        "features": {
            "auth": False,
            "auth_trusted_header": False,
            "enable_api_keys": False,
            "enable_signup": False,
            "enable_login_form": False,
            "enable_websocket": ENABLE_WEBSOCKET_SUPPORT,
            "enable_version_update_check": ENABLE_VERSION_UPDATE_CHECK,
            "enable_public_active_users_count": ENABLE_PUBLIC_ACTIVE_USERS_COUNT,
            "enable_easter_eggs": ENABLE_EASTER_EGGS,
            **(
                {
                    "enable_direct_connections": app.state.config.ENABLE_DIRECT_CONNECTIONS,
                    "enable_folders": app.state.config.ENABLE_FOLDERS,
                    "folder_max_file_count": app.state.config.FOLDER_MAX_FILE_COUNT,
                    "enable_web_search": app.state.config.ENABLE_WEB_SEARCH,
                    "enable_code_execution": app.state.config.ENABLE_CODE_EXECUTION,
                    "enable_code_interpreter": app.state.config.ENABLE_CODE_INTERPRETER,
                    "enable_stable_diffusion": app.state.config.ENABLE_STABLE_DIFFUSION,
                    "enable_music_generation": app.state.config.ENABLE_MUSIC_GENERATION,
                    "enable_video_generation": app.state.config.ENABLE_VIDEO_GENERATION,
                    "enable_autocomplete_generation": app.state.config.ENABLE_AUTOCOMPLETE_GENERATION,
                    "enable_community_sharing": app.state.config.ENABLE_COMMUNITY_SHARING,
                    "enable_admin_export": ENABLE_ADMIN_EXPORT,
                    "enable_admin_chat_access": ENABLE_ADMIN_CHAT_ACCESS,
                    "enable_memories": app.state.config.ENABLE_MEMORIES,
                }
                if user is not None
                else {}
            ),
        },
        **(
            {
                "default_models": app.state.config.DEFAULT_MODELS,
                "default_pinned_models": app.state.config.DEFAULT_PINNED_MODELS,
                "default_prompt_suggestions": app.state.config.DEFAULT_PROMPT_SUGGESTIONS,
                "user_count": user_count,
                "code": {
                    "engine": app.state.config.CODE_EXECUTION_ENGINE,
                    "interpreter_engine": app.state.config.CODE_INTERPRETER_ENGINE,
                },
                "audio": {
                    "tts": {
                        "engine": "",
                        "voice": app.state.config.TTS_VOICE,
                        "split_on": app.state.config.TTS_SPLIT_ON,
                    },
                    "stt": {
                        "engine": "",
                    },
                },
                "file": {
                    "max_size": app.state.config.FILE_MAX_SIZE,
                    "max_count": app.state.config.FILE_MAX_COUNT,
                    "image_compression": {
                        "width": app.state.config.FILE_IMAGE_COMPRESSION_WIDTH,
                        "height": app.state.config.FILE_IMAGE_COMPRESSION_HEIGHT,
                    },
                },
                "permissions": {**app.state.config.USER_PERMISSIONS},
                "ui": {
                    "response_watermark": app.state.config.RESPONSE_WATERMARK,
                },
                "license_metadata": app.state.LICENSE_METADATA,
                **(
                    {
                        "active_entries": app.state.USER_COUNT,
                    }
                    if user.role == "admin"
                    else {}
                ),
            }
            if user is not None and (user.role in ["admin", "user"])
            else {
                **(
                    {
                        "ui": {
                        }
                    }
                    if user and user.role == "pending"
                    else {}
                ),
                **(
                    {
                        "metadata": {
                            "login_footer": app.state.LICENSE_METADATA.get(
                                "login_footer", ""
                            ),
                            "auth_logo_position": app.state.LICENSE_METADATA.get(
                                "auth_logo_position", ""
                            ),
                        }
                    }
                    if app.state.LICENSE_METADATA
                    else {}
                ),
            }
        ),
    }


class UrlForm(BaseModel):
    url: str


@app.post("/api/external/open")
async def open_external_url(form_data: UrlForm, user=Depends(get_verified_user)):
    url = (form_data.url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid external URL",
        )

    opened = await anyio.to_thread.run_sync(lambda: webbrowser.open(parsed.geturl(), new=2))
    return {"status": bool(opened)}


@app.get("/api/version")
async def get_app_version():
    return {
        "version": get_local_project_version(),
        "deployment_id": DEPLOYMENT_ID,
    }


def get_local_project_version():
    version = VERSION
    version_file = BASE_DIR / "version.txt"

    try:
        file_version = version_file.read_text(encoding="utf-8").strip()
        if file_version:
            version = file_version
    except Exception:
        pass

    return version


def normalize_project_version(version: str):
    return (version or "").strip().lstrip("vV")


def get_version_sort_key(version: str):
    normalized = normalize_project_version(version)
    numbers = [int(value) for value in re.findall(r"\d+", normalized)]
    return numbers


def is_project_update_available(current: str, latest: str):
    current_normalized = normalize_project_version(current)
    latest_normalized = normalize_project_version(latest)
    if (
        not current_normalized
        or not latest_normalized
        or current_normalized == "0.0.0"
        or current_normalized == latest_normalized
    ):
        return False

    current_key = get_version_sort_key(current_normalized)
    latest_key = get_version_sort_key(latest_normalized)
    if not current_key or not latest_key:
        return False

    max_len = max(len(current_key), len(latest_key))
    current_key += [0] * (max_len - len(current_key))
    latest_key += [0] * (max_len - len(latest_key))
    return latest_key > current_key


def sanitize_github_release_error(error: Exception):
    response = getattr(error, "response", None)
    if response is not None and getattr(response, "status", None) == 403:
        return "Limite temporário do GitHub atingido. A verificação será tentada novamente depois."

    return str(error)


def get_installed_llamacpp_info():
    version_file = BASE_DIR / "llamacpp-server" / "version.txt"
    tag = ""
    backend = ""
    asset = ""

    try:
        lines = version_file.read_text(encoding="utf-8").splitlines()
        if len(lines) > 0:
            tag = lines[0].strip()
        if len(lines) > 1:
            backend = lines[1].strip()
        if len(lines) > 2:
            asset = lines[2].strip()
    except Exception:
        pass

    return {
        "current": normalize_project_version(tag),
        "current_tag": tag,
        "backend": backend,
        "asset": asset,
    }


async def get_github_latest_release_tag(session, repo: str):
    api_error = None
    try:
        async with session.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            ssl=AIOHTTP_CLIENT_SESSION_SSL,
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return (data.get("tag_name") or "").strip()
    except Exception as e:
        api_error = e

    try:
        async with session.get(
            f"https://github.com/{repo}/releases/latest",
            allow_redirects=False,
            ssl=AIOHTTP_CLIENT_SESSION_SSL,
        ) as response:
            location = response.headers.get("Location", "")
            match = re.search(r"/releases/tag/([^/?#]+)", location)
            if match:
                return unquote(match.group(1)).strip()
    except Exception:
        pass

    raise api_error


LLAMACPP_WINDOWS_BACKENDS = (
    "cpu",
    "cuda-12.4",
    "cuda-13.3",
    "cuda-cu12.4",
    "cuda-cu13.3",
    "vulkan",
)


def is_compatible_llamacpp_release(release: dict):
    if not isinstance(release, dict) or release.get("draft"):
        return False

    tag = (release.get("tag_name") or "").strip()
    if not tag:
        return False

    asset_pattern = re.compile(
        rf"^llama-{re.escape(tag)}-bin-win-"
        rf"(?:{'|'.join(re.escape(value) for value in LLAMACPP_WINDOWS_BACKENDS)})"
        r"-x64\.zip$",
        re.IGNORECASE,
    )
    return any(
        asset_pattern.match((asset.get("name") or "").strip())
        for asset in release.get("assets") or []
        if isinstance(asset, dict)
    )


async def get_github_latest_compatible_llamacpp_release_tag(session):
    api_error = None
    try:
        async with session.get(
            "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30",
            ssl=AIOHTTP_CLIENT_SESSION_SSL,
        ) as response:
            response.raise_for_status()
            releases = await response.json()
            for release in releases if isinstance(releases, list) else []:
                if is_compatible_llamacpp_release(release):
                    return (release.get("tag_name") or "").strip()
            raise RuntimeError(
                "Nenhuma release recente do llama.cpp contém binários Windows compatíveis."
            )
    except Exception as e:
        api_error = e

    # The Atom feed includes pre-releases and remains useful when the API is rate-limited.
    try:
        async with session.get(
            "https://github.com/ggml-org/llama.cpp/releases.atom",
            ssl=AIOHTTP_CLIENT_SESSION_SSL,
        ) as response:
            response.raise_for_status()
            feed = await response.text()
            for encoded_tag in re.findall(r"/releases/tag/([^\"<]+)", feed):
                tag = unquote(encoded_tag).strip()
                if re.fullmatch(r"b\d+", tag, re.IGNORECASE):
                    return tag
    except Exception:
        pass

    raise api_error


def launch_installer_update_page():
    import subprocess

    installer_path = BASE_DIR / "launchers" / "instalar.vbs"
    if not installer_path.exists():
        raise FileNotFoundError(f"instalar.vbs não encontrado em {installer_path}")

    command = [
        os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "wscript.exe",
        ),
        "//nologo",
        str(installer_path),
        "--page",
        "update",
    ]
    subprocess.Popen(
        command,
        cwd=str(BASE_DIR),
        close_fds=True,
    )


@app.post("/api/shutdown")
async def shutdown_app(background_tasks: BackgroundTasks, user=Depends(get_admin_user)):
    """Encerra o servidor NeveAI (backend + llama-server). Apenas admins."""
    import signal
    import psutil

    def _do_shutdown():
        import time
        time.sleep(0.5)  # dá tempo para a resposta HTTP ser enviada
        # Encerra processos llama-server
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info["name"] and "llama-server" in proc.info["name"].lower():
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # Encerra a janela do navegador (browser-app) lançada pelo neve_window
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                cmdline = proc.cmdline()
                joined = " ".join(cmdline).lower()
                if (
                    "logs\\browser-app" in joined
                    or "logs/browser-app" in joined
                    or "--app=http://localhost:8080" in joined
                ):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                pass
        # Encerra o próprio processo uvicorn
        os.kill(os.getpid(), signal.SIGTERM)

    background_tasks.add_task(_do_shutdown)
    return {"status": True, "message": "Shutting down"}


@app.post("/api/updater/start")
async def start_app_updater(user=Depends(get_admin_user)):
    """Abre o hub direto em Atualizar. O instalador encerra o app somente ao iniciar a ação."""
    try:
        await anyio.to_thread.run_sync(launch_installer_update_page)
    except Exception as e:
        log.exception("Failed to launch NeveAI updater")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao abrir o atualizador: {e}",
        )

    return {"status": True, "message": "Updater opened"}


@app.get("/api/version/updates")
async def get_app_latest_release_version(user=Depends(get_verified_user)):
    current_version = get_local_project_version()
    current_version_normalized = normalize_project_version(current_version)
    llama_cpp = get_installed_llamacpp_info()
    latest_version = current_version
    latest_llama_tag = llama_cpp["current_tag"]
    neve_update_available = False
    llama_update_available = False

    if not ENABLE_VERSION_UPDATE_CHECK:
        log.debug(
            f"Version update check is disabled, returning current version as latest version"
        )
        return {
            "current": current_version_normalized,
            "latest": current_version_normalized,
            "current_tag": current_version,
            "latest_tag": current_version,
            "neve_update_available": False,
            "update_available": False,
            "llama_cpp": {
                **llama_cpp,
                "latest": normalize_project_version(latest_llama_tag),
                "latest_tag": latest_llama_tag,
                "update_available": False,
            },
        }

    timeout = aiohttp.ClientTimeout(total=8)
    try:
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            try:
                latest_version = await get_github_latest_release_tag(session, "Etamus/NeveAI")
                neve_update_available = is_project_update_available(
                    current_version, latest_version
                )
            except Exception as e:
                log.debug(e)
                latest_version = current_version

            try:
                latest_llama_tag = (
                    await get_github_latest_compatible_llamacpp_release_tag(session)
                )
                llama_update_available = is_project_update_available(
                    llama_cpp["current_tag"], latest_llama_tag
                )
            except Exception as e:
                log.debug(e)
                latest_llama_tag = llama_cpp["current_tag"]
    except Exception as e:
        log.debug(e)

    return {
        "current": current_version_normalized,
        "latest": normalize_project_version(latest_version),
        "current_tag": current_version,
        "latest_tag": latest_version,
        "neve_update_available": neve_update_available,
        "update_available": neve_update_available or llama_update_available,
        "llama_cpp": {
            **llama_cpp,
            "latest": normalize_project_version(latest_llama_tag),
            "latest_tag": latest_llama_tag,
            "update_available": llama_update_available,
        }
    }


@app.get("/api/changelog")
async def get_app_changelog():
    return {key: CHANGELOG[key] for idx, key in enumerate(CHANGELOG) if idx < 5}


@app.get("/api/usage")
async def get_current_usage(user=Depends(get_verified_user)):
    """
    Get current usage statistics for Neve.
    This is an experimental endpoint and subject to change.
    """
    try:
        # If public visibility is disabled, only allow admins to access this endpoint
        if not ENABLE_PUBLIC_ACTIVE_USERS_COUNT and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Only administrators can view usage statistics.",
            )

        return {
            "model_ids": get_models_in_use(),
            "user_count": Users.get_active_user_count(),
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error getting usage statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


############################
# OAuth Login & Callback
############################


# Initialize OAuth client manager with any MCP tool servers using OAuth 2.1
if len(app.state.config.TOOL_SERVER_CONNECTIONS) > 0:
    for tool_server_connection in app.state.config.TOOL_SERVER_CONNECTIONS:
        if tool_server_connection.get("type", "openapi") == "mcp":
            server_id = tool_server_connection.get("info", {}).get("id")
            auth_type = tool_server_connection.get("auth_type", "none")

            if server_id and auth_type == "oauth_2.1":
                oauth_client_info = tool_server_connection.get("info", {}).get(
                    "oauth_client_info", ""
                )

                try:
                    oauth_client_info = decrypt_data(oauth_client_info)
                    app.state.oauth_client_manager.add_client(
                        f"mcp:{server_id}",
                        OAuthClientInformationFull(**oauth_client_info),
                    )
                except Exception as e:
                    log.error(
                        f"Error adding OAuth client for MCP tool server {server_id}: {e}"
                    )
                    pass

app.add_middleware(
    SessionMiddleware,
    secret_key=NEVEAI_SECRET_KEY,
    session_cookie="owui-session",
    same_site=NEVEAI_SESSION_COOKIE_SAME_SITE,
    https_only=NEVEAI_SESSION_COOKIE_SECURE,
)


async def register_client(request, client_id: str) -> bool:
    server_type, server_id = client_id.split(":", 1)

    connection = None
    connection_idx = None

    for idx, conn in enumerate(request.app.state.config.TOOL_SERVER_CONNECTIONS or []):
        if conn.get("type", "openapi") == server_type:
            info = conn.get("info", {})
            if info.get("id") == server_id:
                connection = conn
                connection_idx = idx
                break

    if connection is None or connection_idx is None:
        log.warning(
            f"Unable to locate MCP tool server configuration for client {client_id} during re-registration"
        )
        return False

    server_url = connection.get("url")
    oauth_server_key = (connection.get("config") or {}).get("oauth_server_key")

    try:
        oauth_client_info = (
            await get_oauth_client_info_with_dynamic_client_registration(
                request,
                client_id,
                server_url,
                oauth_server_key,
            )
        )
    except Exception as e:
        log.error(f"Dynamic client re-registration failed for {client_id}: {e}")
        return False

    try:
        request.app.state.config.TOOL_SERVER_CONNECTIONS[connection_idx] = {
            **connection,
            "info": {
                **connection.get("info", {}),
                "oauth_client_info": encrypt_data(
                    oauth_client_info.model_dump(mode="json")
                ),
            },
        }
    except Exception as e:
        log.error(
            f"Failed to persist updated OAuth client info for tool server {client_id}: {e}"
        )
        return False

    oauth_client_manager.remove_client(client_id)
    oauth_client_manager.add_client(client_id, oauth_client_info)
    log.info(f"Re-registered OAuth client {client_id} for tool server")
    return True


@app.get("/oauth/clients/{client_id}/authorize")
async def oauth_client_authorize(
    client_id: str,
    request: Request,
    response: Response,
    user=Depends(get_verified_user),
):
    # ensure_valid_client_registration
    client = oauth_client_manager.get_client(client_id)
    client_info = oauth_client_manager.get_client_info(client_id)
    if client is None or client_info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    if not await oauth_client_manager._preflight_authorization_url(client, client_info):
        log.info(
            "Detected invalid OAuth client %s; attempting re-registration",
            client_id,
        )

        registered = await register_client(request, client_id)
        if not registered:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to re-register OAuth client",
            )

        client = oauth_client_manager.get_client(client_id)
        client_info = oauth_client_manager.get_client_info(client_id)
        if client is None or client_info is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth client unavailable after re-registration",
            )

        if not await oauth_client_manager._preflight_authorization_url(
            client, client_info
        ):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth client registration is still invalid after re-registration",
            )

    return await oauth_client_manager.handle_authorize(request, client_id=client_id)


@app.get("/oauth/clients/{client_id}/callback")
async def oauth_client_callback(
    client_id: str,
    request: Request,
    response: Response,
    user=Depends(get_verified_user),
):
    return await oauth_client_manager.handle_callback(
        request,
        client_id=client_id,
        user_id=user.id if user else None,
        response=response,
    )


@app.get("/manifest.json")
async def get_manifest_json():
    if app.state.EXTERNAL_PWA_MANIFEST_URL:
        return requests.get(app.state.EXTERNAL_PWA_MANIFEST_URL).json()
    else:
        return {
            "name": app.state.NEVEAI_NAME,
            "short_name": app.state.NEVEAI_NAME,
            "description": f"{app.state.NEVEAI_NAME} is a private, local-first AI workspace.",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#343541",
            "icons": [
                {
                    "src": "/static/logo.png",
                    "type": "image/png",
                    "sizes": "500x500",
                    "purpose": "any",
                },
                {
                    "src": "/static/logo.png",
                    "type": "image/png",
                    "sizes": "500x500",
                    "purpose": "maskable",
                },
            ],
            "share_target": {
                "action": "/",
                "method": "GET",
                "params": {"text": "shared"},
            },
        }


@app.get("/health")
async def healthcheck():
    return {"status": True}


@app.get("/health/db")
async def healthcheck_with_db():
    ScopedSession.execute(text("SELECT 1;")).all()
    return {"status": True}


mimetypes.add_type("image/webp", ".webp")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/cache/{path:path}")
async def serve_cache_file(
    path: str,
    user=Depends(get_verified_user),
):
    file_path = os.path.abspath(os.path.join(CACHE_DIR, path))
    # prevent path traversal
    if not file_path.startswith(os.path.abspath(CACHE_DIR)):
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


def swagger_ui_html(*args, **kwargs):
    return get_swagger_ui_html(
        *args,
        **kwargs,
        swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui/swagger-ui.css",
        swagger_favicon_url="/static/swagger-ui/favicon.png",
    )


applications.get_swagger_ui_html = swagger_ui_html

if os.path.exists(FRONTEND_BUILD_DIR):
    mimetypes.add_type("text/javascript", ".js")
    app.mount(
        "/",
        SPAStaticFiles(directory=FRONTEND_BUILD_DIR, html=True),
        name="spa-static-files",
    )
else:
    log.warning(
        f"Frontend build directory not found at '{FRONTEND_BUILD_DIR}'. Serving API only."
    )
