import json
import logging
import os
import shutil
import base64
import redis

from datetime import datetime
from pathlib import Path
from typing import Generic, Union, Optional, TypeVar
from urllib.parse import urlparse

import requests
from pydantic import BaseModel
from sqlalchemy import JSON, Column, DateTime, Integer, func
from neveai.env import (
    DATA_DIR,
    DATABASE_URL,
    ENABLE_DB_MIGRATIONS,
    ENV,
    REDIS_URL,
    REDIS_KEY_PREFIX,
    REDIS_SENTINEL_HOSTS,
    REDIS_SENTINEL_PORT,
    FRONTEND_BUILD_DIR,
    OFFLINE_MODE,
    NEVEAI_DIR,
    NEVEAI_FAVICON_URL,
    NEVEAI_NAME,
    log,
)
from neveai.internal.db import Base, get_db
from neveai.utils.redis import get_redis_connection


class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1


# Filter out /endpoint
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

####################################
# Config helpers
####################################


# Function to run the alembic migrations
def run_migrations():
    log.info("Running migrations")
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config(NEVEAI_DIR / "alembic.ini")

        # Set the script location dynamically
        migrations_path = NEVEAI_DIR / "migrations"
        alembic_cfg.set_main_option("script_location", str(migrations_path))

        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        log.exception(f"Error running migrations: {e}")


if ENABLE_DB_MIGRATIONS:
    run_migrations()


class Config(Base):
    __tablename__ = "config"

    id = Column(Integer, primary_key=True)
    data = Column(JSON, nullable=False)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())


def load_json_config():
    with open(f"{DATA_DIR}/config.json", "r") as file:
        return json.load(file)


def save_to_db(data):
    with get_db() as db:
        existing_config = db.query(Config).first()
        if not existing_config:
            new_config = Config(data=data, version=0)
            db.add(new_config)
        else:
            existing_config.data = data
            existing_config.updated_at = datetime.now()
            db.add(existing_config)
        db.commit()


def reset_config():
    with get_db() as db:
        db.query(Config).delete()
        db.commit()


# When initializing, check if config.json exists and migrate it to the database
if os.path.exists(f"{DATA_DIR}/config.json"):
    data = load_json_config()
    save_to_db(data)
    os.rename(f"{DATA_DIR}/config.json", f"{DATA_DIR}/old_config.json")

DEFAULT_CONFIG = {
    "version": 0,
    "ui": {},
}


def get_config():
    with get_db() as db:
        config_entry = db.query(Config).order_by(Config.id.desc()).first()
        return config_entry.data if config_entry else DEFAULT_CONFIG


CONFIG_DATA = get_config()


def get_config_value(config_path: str):
    path_parts = config_path.split(".")
    cur_config = CONFIG_DATA
    for key in path_parts:
        if key in cur_config:
            cur_config = cur_config[key]
        else:
            return None
    return cur_config


PERSISTENT_CONFIG_REGISTRY = []


def save_config(config):
    global CONFIG_DATA
    global PERSISTENT_CONFIG_REGISTRY
    try:
        save_to_db(config)
        CONFIG_DATA = config

        # Trigger updates on all registered PersistentConfig entries
        for config_item in PERSISTENT_CONFIG_REGISTRY:
            config_item.update()
    except Exception as e:
        log.exception(e)
        return False
    return True


T = TypeVar("T")

ENABLE_PERSISTENT_CONFIG = (
    os.environ.get("ENABLE_PERSISTENT_CONFIG", "True").lower() == "true"
)


class PersistentConfig(Generic[T]):
    def __init__(self, env_name: str, config_path: str, env_value: T):
        self.env_name = env_name
        self.config_path = config_path
        self.env_value = env_value
        self.config_value = get_config_value(config_path)

        if self.config_value is not None and ENABLE_PERSISTENT_CONFIG:
            if (
                self.config_path.startswith("oauth.")
                and not ENABLE_OAUTH_PERSISTENT_CONFIG
            ):
                log.info(
                    f"Skipping loading of '{env_name}' as OAuth persistent config is disabled"
                )
                self.value = env_value
            else:
                log.info(f"'{env_name}' loaded from the latest database entry")
                self.value = self.config_value
        else:
            self.value = env_value

        PERSISTENT_CONFIG_REGISTRY.append(self)

    def __str__(self):
        return str(self.value)

    @property
    def __dict__(self):
        raise TypeError(
            "PersistentConfig object cannot be converted to dict, use config_get or .value instead."
        )

    def __getattribute__(self, item):
        if item == "__dict__":
            raise TypeError(
                "PersistentConfig object cannot be converted to dict, use config_get or .value instead."
            )
        return super().__getattribute__(item)

    def update(self):
        new_value = get_config_value(self.config_path)
        if new_value is not None:
            self.value = new_value
            log.info(f"Updated {self.env_name} to new value {self.value}")

    def save(self):
        log.info(f"Saving '{self.env_name}' to the database")
        path_parts = self.config_path.split(".")
        sub_config = CONFIG_DATA
        for key in path_parts[:-1]:
            if key not in sub_config:
                sub_config[key] = {}
            sub_config = sub_config[key]
        sub_config[path_parts[-1]] = self.value
        save_to_db(CONFIG_DATA)
        self.config_value = self.value


class AppConfig:
    _redis: Union[redis.Redis, redis.cluster.RedisCluster] = None
    _redis_key_prefix: str

    _state: dict[str, PersistentConfig]

    def __init__(
        self,
        redis_url: Optional[str] = None,
        redis_sentinels: Optional[list] = [],
        redis_cluster: Optional[bool] = False,
        redis_key_prefix: str = "neveai",
    ):
        if redis_url:
            super().__setattr__("_redis_key_prefix", redis_key_prefix)
            super().__setattr__(
                "_redis",
                get_redis_connection(
                    redis_url,
                    redis_sentinels,
                    redis_cluster,
                    decode_responses=True,
                ),
            )

        super().__setattr__("_state", {})

    def __setattr__(self, key, value):
        if isinstance(value, PersistentConfig):
            self._state[key] = value
        else:
            self._state[key].value = value
            self._state[key].save()

            if self._redis and ENABLE_PERSISTENT_CONFIG:
                redis_key = f"{self._redis_key_prefix}:config:{key}"
                self._redis.set(redis_key, json.dumps(self._state[key].value))

    def __getattr__(self, key):
        if key not in self._state:
            raise AttributeError(f"Config key '{key}' not found")

        # If Redis is available and persistent config is enabled, check for an updated value
        if self._redis and ENABLE_PERSISTENT_CONFIG:
            redis_key = f"{self._redis_key_prefix}:config:{key}"
            redis_value = self._redis.get(redis_key)

            if redis_value is not None:
                try:
                    decoded_value = json.loads(redis_value)

                    # Update the in-memory value if different
                    if self._state[key].value != decoded_value:
                        self._state[key].value = decoded_value
                        log.info(f"Updated {key} from Redis: {decoded_value}")

                except json.JSONDecodeError:
                    log.error(f"Invalid JSON format in Redis for {key}: {redis_value}")

        return self._state[key].value


JWT_EXPIRES_IN = PersistentConfig(
    "JWT_EXPIRES_IN", "auth.jwt_expiry", os.environ.get("JWT_EXPIRES_IN", "4w")
)

if JWT_EXPIRES_IN.value == "-1":
    log.warning(
        "⚠️  SECURITY WARNING: JWT_EXPIRES_IN is set to '-1'\n"
        "    Tokens will never expire — review this for production deployments.\n"
    )

####################################
# OAuth user login is not part of the local NeveAI runtime.
####################################

ENABLE_OAUTH_PERSISTENT_CONFIG = False

####################################
# Static DIR
####################################

STATIC_DIR = Path(os.getenv("STATIC_DIR", NEVEAI_DIR / "static")).resolve()

try:
    if STATIC_DIR.exists():
        for item in STATIC_DIR.iterdir():
            if item.is_file() or item.is_symlink():
                try:
                    item.unlink()
                except Exception as e:
                    pass
except Exception as e:
    pass

for file_path in (FRONTEND_BUILD_DIR / "static").glob("**/*"):
    if file_path.is_file():
        target_path = STATIC_DIR / file_path.relative_to(
            (FRONTEND_BUILD_DIR / "static")
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(file_path, target_path)
        except Exception as e:
            logging.error(f"An error occurred: {e}")

frontend_favicon = FRONTEND_BUILD_DIR / "static" / "favicon.png"

if frontend_favicon.exists():
    try:
        shutil.copyfile(frontend_favicon, STATIC_DIR / "favicon.png")
    except Exception as e:
        logging.error(f"An error occurred: {e}")

frontend_splash = FRONTEND_BUILD_DIR / "static" / "splash.png"

if frontend_splash.exists():
    try:
        shutil.copyfile(frontend_splash, STATIC_DIR / "splash.png")
    except Exception as e:
        logging.error(f"An error occurred: {e}")

frontend_loader = FRONTEND_BUILD_DIR / "static" / "loader.js"

if frontend_loader.exists():
    try:
        shutil.copyfile(frontend_loader, STATIC_DIR / "loader.js")
    except Exception as e:
        logging.error(f"An error occurred: {e}")


####################################
# CUSTOM_NAME
####################################

CUSTOM_NAME = os.environ.get("CUSTOM_NAME", "")

####################################
# Local Storage
####################################

####################################
# File Upload DIR
####################################

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


####################################
# Cache DIR
####################################

CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


####################################
# DIRECT CONNECTIONS
####################################

ENABLE_DIRECT_CONNECTIONS = PersistentConfig(
    "ENABLE_DIRECT_CONNECTIONS",
    "direct.enable",
    os.environ.get("ENABLE_DIRECT_CONNECTIONS", "False").lower() == "true",
)

####################################
# MODELS
####################################

ENABLE_BASE_MODELS_CACHE = PersistentConfig(
    "ENABLE_BASE_MODELS_CACHE",
    "models.base_models_cache",
    os.environ.get("ENABLE_BASE_MODELS_CACHE", "False").lower() == "true",
)


####################################
# TOOL_SERVERS
####################################

try:
    tool_server_connections = json.loads(
        os.environ.get("TOOL_SERVER_CONNECTIONS", "[]")
    )
except Exception as e:
    log.exception(f"Error loading TOOL_SERVER_CONNECTIONS: {e}")
    tool_server_connections = []


TOOL_SERVER_CONNECTIONS = PersistentConfig(
    "TOOL_SERVER_CONNECTIONS",
    "tool_server.connections",
    tool_server_connections,
)

####################################
# TERMINAL_SERVER
####################################

terminal_server_connections = json.loads(
    os.environ.get("TERMINAL_SERVER_CONNECTIONS", "[]")
)

TERMINAL_SERVER_CONNECTIONS = PersistentConfig(
    "TERMINAL_SERVER_CONNECTIONS",
    "terminal_server.connections",
    terminal_server_connections,
)

####################################
# NEVEAI
####################################


NEVEAI_URL = PersistentConfig("NEVEAI_URL", "webui.url", os.environ.get("NEVE_URL", ""))


DEFAULT_LOCALE = PersistentConfig(
    "DEFAULT_LOCALE",
    "ui.default_locale",
    os.environ.get("DEFAULT_LOCALE", "pt-BR"),
)

DEFAULT_MODELS = PersistentConfig(
    "DEFAULT_MODELS", "ui.default_models", os.environ.get("DEFAULT_MODELS", None)
)

DEFAULT_PINNED_MODELS = PersistentConfig(
    "DEFAULT_PINNED_MODELS",
    "ui.default_pinned_models",
    os.environ.get("DEFAULT_PINNED_MODELS", None),
)

try:
    default_prompt_suggestions = json.loads(
        os.environ.get("DEFAULT_PROMPT_SUGGESTIONS", "[]")
    )
except Exception as e:
    log.exception(f"Error loading DEFAULT_PROMPT_SUGGESTIONS: {e}")
    default_prompt_suggestions = []
if default_prompt_suggestions == []:
    default_prompt_suggestions = [
        {
            "title": ["Me ajude a estudar", "vocabulário para o vestibular"],
            "content": "Me ajude a estudar vocabulário: escreva uma frase para eu completar com a opção correta.",
        },
        {
            "title": ["Me dê ideias", "para usar os desenhos dos meus filhos"],
            "content": "Quais são 5 coisas criativas que posso fazer com os desenhos dos meus filhos? Não quero jogar fora, mas está acumulando muito.",
        },
        {
            "title": ["Me conte uma curiosidade", "sobre o Império Romano"],
            "content": "Me conte uma curiosidade interessante e aleatória sobre o Império Romano.",
        },
        {
            "title": ["Me mostre um trecho de código", "de um cabeçalho fixo em CSS"],
            "content": "Me mostre um trecho de código de um cabeçalho fixo (sticky header) em CSS e JavaScript.",
        },
        {
            "title": ["Explique opções de investimento", "de forma simples"],
            "content": "Explique de forma simples como funcionam opções de investimento na bolsa de valores.",
        },
        {
            "title": ["Vencer a procrastinação", "me dê dicas práticas"],
            "content": "Pode começar me perguntando sobre as situações em que mais procrastino e depois me dar sugestões para superar isso?",
        },
    ]

DEFAULT_PROMPT_SUGGESTIONS = PersistentConfig(
    "DEFAULT_PROMPT_SUGGESTIONS",
    "ui.prompt_suggestions",
    default_prompt_suggestions,
)

MODEL_ORDER_LIST = PersistentConfig(
    "MODEL_ORDER_LIST",
    "ui.model_order_list",
    [],
)

DEFAULT_MODEL_METADATA = PersistentConfig(
    "DEFAULT_MODEL_METADATA",
    "models.default_metadata",
    {},
)

DEFAULT_MODEL_PARAMS = PersistentConfig(
    "DEFAULT_MODEL_PARAMS",
    "models.default_params",
    {},
)

DEFAULT_GROUP_ID = PersistentConfig(
    "DEFAULT_GROUP_ID",
    "ui.default_group_id",
    os.environ.get("DEFAULT_GROUP_ID", ""),
)


RESPONSE_WATERMARK = PersistentConfig(
    "RESPONSE_WATERMARK",
    "ui.watermark",
    os.environ.get("RESPONSE_WATERMARK", ""),
)


USER_PERMISSIONS_WORKSPACE_MODELS_ACCESS = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_MODELS_ACCESS", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_KNOWLEDGE_ACCESS = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_KNOWLEDGE_ACCESS", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_PROMPTS_ACCESS = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_PROMPTS_ACCESS", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_TOOLS_ACCESS = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_TOOLS_ACCESS", "False").lower() == "true"
)

USER_PERMISSIONS_WORKSPACE_SKILLS_ACCESS = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_SKILLS_ACCESS", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_MODELS_IMPORT = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_MODELS_IMPORT", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_MODELS_EXPORT = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_MODELS_EXPORT", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_PROMPTS_IMPORT = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_PROMPTS_IMPORT", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_PROMPTS_EXPORT = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_PROMPTS_EXPORT", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_TOOLS_IMPORT = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_TOOLS_IMPORT", "False").lower() == "true"
)

USER_PERMISSIONS_WORKSPACE_TOOLS_EXPORT = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_TOOLS_EXPORT", "False").lower() == "true"
)


USER_PERMISSIONS_WORKSPACE_MODELS_ALLOW_SHARING = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_MODELS_ALLOW_SHARING", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_MODELS_ALLOW_PUBLIC_SHARING = (
    os.environ.get(
        "USER_PERMISSIONS_WORKSPACE_MODELS_ALLOW_PUBLIC_SHARING", "False"
    ).lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_KNOWLEDGE_ALLOW_SHARING = (
    os.environ.get(
        "USER_PERMISSIONS_WORKSPACE_KNOWLEDGE_ALLOW_SHARING", "False"
    ).lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_KNOWLEDGE_ALLOW_PUBLIC_SHARING = (
    os.environ.get(
        "USER_PERMISSIONS_WORKSPACE_KNOWLEDGE_ALLOW_PUBLIC_SHARING", "False"
    ).lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_PROMPTS_ALLOW_SHARING = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_PROMPTS_ALLOW_SHARING", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_PROMPTS_ALLOW_PUBLIC_SHARING = (
    os.environ.get(
        "USER_PERMISSIONS_WORKSPACE_PROMPTS_ALLOW_PUBLIC_SHARING", "False"
    ).lower()
    == "true"
)


USER_PERMISSIONS_WORKSPACE_TOOLS_ALLOW_SHARING = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_TOOLS_ALLOW_SHARING", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_TOOLS_ALLOW_PUBLIC_SHARING = (
    os.environ.get(
        "USER_PERMISSIONS_WORKSPACE_TOOLS_ALLOW_PUBLIC_SHARING", "False"
    ).lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_SKILLS_ALLOW_SHARING = (
    os.environ.get("USER_PERMISSIONS_WORKSPACE_SKILLS_ALLOW_SHARING", "False").lower()
    == "true"
)

USER_PERMISSIONS_WORKSPACE_SKILLS_ALLOW_PUBLIC_SHARING = (
    os.environ.get(
        "USER_PERMISSIONS_WORKSPACE_SKILLS_ALLOW_PUBLIC_SHARING", "False"
    ).lower()
    == "true"
)


USER_PERMISSIONS_NOTES_ALLOW_SHARING = (
    os.environ.get("USER_PERMISSIONS_NOTES_ALLOW_SHARING", "False").lower() == "true"
)

USER_PERMISSIONS_NOTES_ALLOW_PUBLIC_SHARING = (
    os.environ.get("USER_PERMISSIONS_NOTES_ALLOW_PUBLIC_SHARING", "False").lower()
    == "true"
)

USER_PERMISSIONS_ACCESS_GRANTS_ALLOW_USERS = (
    os.environ.get("USER_PERMISSIONS_ACCESS_GRANTS_ALLOW_USERS", "True").lower()
    == "true"
)


USER_PERMISSIONS_CHAT_CONTROLS = (
    os.environ.get("USER_PERMISSIONS_CHAT_CONTROLS", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_VALVES = (
    os.environ.get("USER_PERMISSIONS_CHAT_VALVES", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_SYSTEM_PROMPT = (
    os.environ.get("USER_PERMISSIONS_CHAT_SYSTEM_PROMPT", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_PARAMS = (
    os.environ.get("USER_PERMISSIONS_CHAT_PARAMS", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_FILE_UPLOAD = (
    os.environ.get("USER_PERMISSIONS_CHAT_FILE_UPLOAD", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_WEB_UPLOAD = (
    os.environ.get("USER_PERMISSIONS_CHAT_WEB_UPLOAD", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_DELETE = (
    os.environ.get("USER_PERMISSIONS_CHAT_DELETE", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_DELETE_MESSAGE = (
    os.environ.get("USER_PERMISSIONS_CHAT_DELETE_MESSAGE", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_CONTINUE_RESPONSE = (
    os.environ.get("USER_PERMISSIONS_CHAT_CONTINUE_RESPONSE", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_REGENERATE_RESPONSE = (
    os.environ.get("USER_PERMISSIONS_CHAT_REGENERATE_RESPONSE", "True").lower()
    == "true"
)

USER_PERMISSIONS_CHAT_RATE_RESPONSE = (
    os.environ.get("USER_PERMISSIONS_CHAT_RATE_RESPONSE", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_EDIT = (
    os.environ.get("USER_PERMISSIONS_CHAT_EDIT", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_SHARE = (
    os.environ.get("USER_PERMISSIONS_CHAT_SHARE", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_EXPORT = (
    os.environ.get("USER_PERMISSIONS_CHAT_EXPORT", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_STT = (
    os.environ.get("USER_PERMISSIONS_CHAT_STT", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_TTS = (
    os.environ.get("USER_PERMISSIONS_CHAT_TTS", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_CALL = (
    os.environ.get("USER_PERMISSIONS_CHAT_CALL", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_MULTIPLE_MODELS = (
    os.environ.get("USER_PERMISSIONS_CHAT_MULTIPLE_MODELS", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_TEMPORARY = (
    os.environ.get("USER_PERMISSIONS_CHAT_TEMPORARY", "True").lower() == "true"
)

USER_PERMISSIONS_CHAT_TEMPORARY_ENFORCED = (
    os.environ.get("USER_PERMISSIONS_CHAT_TEMPORARY_ENFORCED", "False").lower()
    == "true"
)


USER_PERMISSIONS_FEATURES_DIRECT_TOOL_SERVERS = (
    os.environ.get("USER_PERMISSIONS_FEATURES_DIRECT_TOOL_SERVERS", "False").lower()
    == "true"
)

USER_PERMISSIONS_FEATURES_WEB_SEARCH = (
    os.environ.get("USER_PERMISSIONS_FEATURES_WEB_SEARCH", "True").lower() == "true"
)


USER_PERMISSIONS_FEATURES_CODE_INTERPRETER = (
    os.environ.get("USER_PERMISSIONS_FEATURES_CODE_INTERPRETER", "True").lower()
    == "true"
)

USER_PERMISSIONS_FEATURES_FOLDERS = (
    os.environ.get("USER_PERMISSIONS_FEATURES_FOLDERS", "True").lower() == "true"
)


USER_PERMISSIONS_FEATURES_MEMORIES = (
    os.environ.get("USER_PERMISSIONS_FEATURES_MEMORIES", "True").lower() == "true"
)

USER_PERMISSIONS_FEATURES_STABLE_DIFFUSION = (
    os.environ.get("USER_PERMISSIONS_FEATURES_STABLE_DIFFUSION", "True").lower() == "true"
)

USER_PERMISSIONS_FEATURES_MUSIC_GENERATION = (
    os.environ.get("USER_PERMISSIONS_FEATURES_MUSIC_GENERATION", "True").lower() == "true"
)

USER_PERMISSIONS_FEATURES_VIDEO_GENERATION = (
    os.environ.get("USER_PERMISSIONS_FEATURES_VIDEO_GENERATION", "True").lower() == "true"
)


USER_PERMISSIONS_SETTINGS_INTERFACE = (
    os.environ.get("USER_PERMISSIONS_SETTINGS_INTERFACE", "True").lower() == "true"
)


DEFAULT_USER_PERMISSIONS = {
    "workspace": {
        "models": USER_PERMISSIONS_WORKSPACE_MODELS_ACCESS,
        "knowledge": USER_PERMISSIONS_WORKSPACE_KNOWLEDGE_ACCESS,
        "prompts": USER_PERMISSIONS_WORKSPACE_PROMPTS_ACCESS,
        "tools": USER_PERMISSIONS_WORKSPACE_TOOLS_ACCESS,
        "skills": USER_PERMISSIONS_WORKSPACE_SKILLS_ACCESS,
        "models_import": USER_PERMISSIONS_WORKSPACE_MODELS_IMPORT,
        "models_export": USER_PERMISSIONS_WORKSPACE_MODELS_EXPORT,
        "prompts_import": USER_PERMISSIONS_WORKSPACE_PROMPTS_IMPORT,
        "prompts_export": USER_PERMISSIONS_WORKSPACE_PROMPTS_EXPORT,
        "tools_import": USER_PERMISSIONS_WORKSPACE_TOOLS_IMPORT,
        "tools_export": USER_PERMISSIONS_WORKSPACE_TOOLS_EXPORT,
    },
    "sharing": {
        "models": USER_PERMISSIONS_WORKSPACE_MODELS_ALLOW_SHARING,
        "public_models": USER_PERMISSIONS_WORKSPACE_MODELS_ALLOW_PUBLIC_SHARING,
        "knowledge": USER_PERMISSIONS_WORKSPACE_KNOWLEDGE_ALLOW_SHARING,
        "public_knowledge": USER_PERMISSIONS_WORKSPACE_KNOWLEDGE_ALLOW_PUBLIC_SHARING,
        "prompts": USER_PERMISSIONS_WORKSPACE_PROMPTS_ALLOW_SHARING,
        "public_prompts": USER_PERMISSIONS_WORKSPACE_PROMPTS_ALLOW_PUBLIC_SHARING,
        "tools": USER_PERMISSIONS_WORKSPACE_TOOLS_ALLOW_SHARING,
        "public_tools": USER_PERMISSIONS_WORKSPACE_TOOLS_ALLOW_PUBLIC_SHARING,
        "skills": USER_PERMISSIONS_WORKSPACE_SKILLS_ALLOW_SHARING,
        "public_skills": USER_PERMISSIONS_WORKSPACE_SKILLS_ALLOW_PUBLIC_SHARING,
        "notes": USER_PERMISSIONS_NOTES_ALLOW_SHARING,
        "public_notes": USER_PERMISSIONS_NOTES_ALLOW_PUBLIC_SHARING,
    },
    "access_grants": {
        "allow_users": USER_PERMISSIONS_ACCESS_GRANTS_ALLOW_USERS,
    },
    "chat": {
        "controls": USER_PERMISSIONS_CHAT_CONTROLS,
        "valves": USER_PERMISSIONS_CHAT_VALVES,
        "system_prompt": USER_PERMISSIONS_CHAT_SYSTEM_PROMPT,
        "params": USER_PERMISSIONS_CHAT_PARAMS,
        "file_upload": USER_PERMISSIONS_CHAT_FILE_UPLOAD,
        "web_upload": USER_PERMISSIONS_CHAT_WEB_UPLOAD,
        "delete": USER_PERMISSIONS_CHAT_DELETE,
        "delete_message": USER_PERMISSIONS_CHAT_DELETE_MESSAGE,
        "continue_response": USER_PERMISSIONS_CHAT_CONTINUE_RESPONSE,
        "regenerate_response": USER_PERMISSIONS_CHAT_REGENERATE_RESPONSE,
        "rate_response": USER_PERMISSIONS_CHAT_RATE_RESPONSE,
        "edit": USER_PERMISSIONS_CHAT_EDIT,
        "share": USER_PERMISSIONS_CHAT_SHARE,
        "export": USER_PERMISSIONS_CHAT_EXPORT,
        "stt": USER_PERMISSIONS_CHAT_STT,
        "tts": USER_PERMISSIONS_CHAT_TTS,
        "call": USER_PERMISSIONS_CHAT_CALL,
        "multiple_models": USER_PERMISSIONS_CHAT_MULTIPLE_MODELS,
        "temporary": USER_PERMISSIONS_CHAT_TEMPORARY,
        "temporary_enforced": USER_PERMISSIONS_CHAT_TEMPORARY_ENFORCED,
    },
    "features": {
        # General features
        "folders": USER_PERMISSIONS_FEATURES_FOLDERS,
        "direct_tool_servers": USER_PERMISSIONS_FEATURES_DIRECT_TOOL_SERVERS,
        # Chat features
        "web_search": USER_PERMISSIONS_FEATURES_WEB_SEARCH,
        "code_interpreter": USER_PERMISSIONS_FEATURES_CODE_INTERPRETER,
        "memories": USER_PERMISSIONS_FEATURES_MEMORIES,
        "stable_diffusion": USER_PERMISSIONS_FEATURES_STABLE_DIFFUSION,
        "music_generation": USER_PERMISSIONS_FEATURES_MUSIC_GENERATION,
        "video_generation": USER_PERMISSIONS_FEATURES_VIDEO_GENERATION,
    },
    "settings": {
        "interface": USER_PERMISSIONS_SETTINGS_INTERFACE,
    },
}

USER_PERMISSIONS = PersistentConfig(
    "USER_PERMISSIONS",
    "user.permissions",
    DEFAULT_USER_PERMISSIONS,
)

ENABLE_FOLDERS = PersistentConfig(
    "ENABLE_FOLDERS",
    "folders.enable",
    os.environ.get("ENABLE_FOLDERS", "True").lower() == "true",
)

FOLDER_MAX_FILE_COUNT = PersistentConfig(
    "FOLDER_MAX_FILE_COUNT",
    "folders.max_file_count",
    os.environ.get("FOLDER_MAX_FILE_COUNT", ""),
)

ENABLE_ADMIN_EXPORT = os.environ.get("ENABLE_ADMIN_EXPORT", "True").lower() == "true"

ENABLE_ADMIN_WORKSPACE_CONTENT_ACCESS = (
    os.environ.get("ENABLE_ADMIN_WORKSPACE_CONTENT_ACCESS", "True").lower() == "true"
)

BYPASS_ADMIN_ACCESS_CONTROL = (
    os.environ.get(
        "BYPASS_ADMIN_ACCESS_CONTROL",
        os.environ.get("ENABLE_ADMIN_WORKSPACE_CONTENT_ACCESS", "True"),
    ).lower()
    == "true"
)

ENABLE_ADMIN_CHAT_ACCESS = (
    os.environ.get("ENABLE_ADMIN_CHAT_ACCESS", "True").lower() == "true"
)

ENABLE_COMMUNITY_SHARING = PersistentConfig(
    "ENABLE_COMMUNITY_SHARING",
    "ui.enable_community_sharing",
    os.environ.get("ENABLE_COMMUNITY_SHARING", "True").lower() == "true",
)

# FastAPI / AnyIO settings
THREAD_POOL_SIZE = os.getenv("THREAD_POOL_SIZE", None)

if THREAD_POOL_SIZE is not None and isinstance(THREAD_POOL_SIZE, str):
    try:
        THREAD_POOL_SIZE = int(THREAD_POOL_SIZE)
    except ValueError:
        log.warning(
            f"THREAD_POOL_SIZE is not a valid integer: {THREAD_POOL_SIZE}. Defaulting to None."
        )
        THREAD_POOL_SIZE = None


def validate_cors_origin(origin):
    parsed_url = urlparse(origin)

    # Check if the scheme is either http or https, or a custom scheme
    schemes = ["http", "https"] + CORS_ALLOW_CUSTOM_SCHEME
    if parsed_url.scheme not in schemes:
        raise ValueError(
            f"Invalid scheme in CORS_ALLOW_ORIGIN: '{origin}'. Only 'http' and 'https' and CORS_ALLOW_CUSTOM_SCHEME are allowed."
        )

    # Ensure that the netloc (domain + port) is present, indicating it's a valid URL
    if not parsed_url.netloc:
        raise ValueError(f"Invalid URL structure in CORS_ALLOW_ORIGIN: '{origin}'.")


# For production, you should only need one host as
# fastapi serves the svelte-kit built frontend and backend from the same host and port.
# To test CORS_ALLOW_ORIGIN locally, you can set something like
# CORS_ALLOW_ORIGIN=http://localhost:5173;http://localhost:8080
# in your .env file depending on your frontend port, 5173 in this case.
CORS_ALLOW_ORIGIN = os.environ.get("CORS_ALLOW_ORIGIN", "*").split(";")

# Allows custom URL schemes (e.g., app://) to be used as origins for CORS.
# Useful for local development or desktop clients with schemes like app:// or other custom protocols.
# Provide a semicolon-separated list of allowed schemes in the environment variable CORS_ALLOW_CUSTOM_SCHEMES.
CORS_ALLOW_CUSTOM_SCHEME = os.environ.get("CORS_ALLOW_CUSTOM_SCHEME", "").split(";")

if CORS_ALLOW_ORIGIN == ["*"]:
    log.warning(
        "\n\nWARNING: CORS_ALLOW_ORIGIN IS SET TO '*' - NOT RECOMMENDED FOR PRODUCTION DEPLOYMENTS.\n"
    )
else:
    # You have to pick between a single wildcard or a list of origins.
    # Doing both will result in CORS errors in the browser.
    for origin in CORS_ALLOW_ORIGIN:
        validate_cors_origin(origin)


class BannerModel(BaseModel):
    id: str
    type: str
    title: Optional[str] = None
    content: str
    dismissible: bool
    timestamp: int


try:
    banners = json.loads(os.environ.get("NEVE_BANNERS", "[]"))
    banners = [BannerModel(**banner) for banner in banners]
except Exception as e:
    log.exception(f"Error loading NEVE_BANNERS: {e}")
    banners = []

NEVEAI_BANNERS = PersistentConfig("NEVEAI_BANNERS", "ui.banners", banners)



####################################
# TASKS
####################################


TASK_MODEL = PersistentConfig(
    "TASK_MODEL",
    "task.model.default",
    os.environ.get("TASK_MODEL", ""),
)

TASK_MODEL_EXTERNAL = PersistentConfig(
    "TASK_MODEL_EXTERNAL",
    "task.model.external",
    os.environ.get("TASK_MODEL_EXTERNAL", ""),
)

TITLE_GENERATION_PROMPT_TEMPLATE = PersistentConfig(
    "TITLE_GENERATION_PROMPT_TEMPLATE",
    "task.title.prompt_template",
    os.environ.get("TITLE_GENERATION_PROMPT_TEMPLATE", ""),
)

DEFAULT_TITLE_GENERATION_PROMPT_TEMPLATE = """### Tarefa:
Gere um título conciso de 3 a 5 palavras com um emoji que resuma o histórico do chat.
### Diretrizes:
- O título deve representar claramente o tema ou assunto principal da conversa.
- Use emojis que melhorem a compreensão do tópico, mas evite aspas ou formatação especial.
- Escreva o título **sempre em português brasileiro**, independentemente do idioma da conversa.
- Priorize precisão em vez de criatividade excessiva; mantenha simples e claro.
- Toda a sua resposta deve consistir apenas do objeto JSON, sem texto introdutório ou conclusivo.
- A saída deve ser um único objeto JSON bruto, sem cercas de código markdown ou outro texto encapsulador.
- Garanta que nenhum texto de conversa, afirmações ou explicações precedam ou sigam a saída JSON bruta, pois isso causará falha direta na análise.
### Saída:
Formato JSON: { "title": "seu título conciso aqui" }
### Exemplos:
- { "title": "📉 Tendências do Mercado de Ações" },
- { "title": "🍪 Receita de Biscoito de Chocolate" },
- { "title": "Evolução do Streaming de Música" },
- { "title": "Dicas de Produtividade no Home Office" },
- { "title": "Inteligência Artificial na Saúde" },
- { "title": "🎮 Desenvolvimento de Jogos Digitais" }
### Histórico do Chat:
<chat_history>
{{MESSAGES:END:2}}
</chat_history>"""

IMAGE_PROMPT_GENERATION_PROMPT_TEMPLATE = PersistentConfig(
    "IMAGE_PROMPT_GENERATION_PROMPT_TEMPLATE",
    "task.image.prompt_template",
    os.environ.get("IMAGE_PROMPT_GENERATION_PROMPT_TEMPLATE", ""),
)

DEFAULT_IMAGE_PROMPT_GENERATION_PROMPT_TEMPLATE = """### Task:
Generate a detailed prompt for am image generation task based on the given language and context. Describe the image as if you were explaining it to someone who cannot see it. Include relevant details, colors, shapes, and any other important elements.

### Guidelines:
- Be descriptive and detailed, focusing on the most important aspects of the image.
- Avoid making assumptions or adding information not present in the image.
- Use the chat's primary language; default to English if multilingual.
- If the image is too complex, focus on the most prominent elements.

### Output:
Strictly return in JSON format:
{
    "prompt": "Your detailed description here."
}

### Chat History:
<chat_history>
{{MESSAGES:END:6}}
</chat_history>"""


FOLLOW_UP_GENERATION_PROMPT_TEMPLATE = PersistentConfig(
    "FOLLOW_UP_GENERATION_PROMPT_TEMPLATE",
    "task.follow_up.prompt_template",
    os.environ.get("FOLLOW_UP_GENERATION_PROMPT_TEMPLATE", ""),
)

DEFAULT_FOLLOW_UP_GENERATION_PROMPT_TEMPLATE = """### Task:
Suggest 3-5 relevant follow-up questions or prompts that the user might naturally ask next in this conversation as a **user**, based on the chat history, to help continue or deepen the discussion.
### Guidelines:
- Write all follow-up questions from the user’s point of view, directed to the assistant.
- Make questions concise, clear, and directly related to the discussed topic(s).
- Only suggest follow-ups that make sense given the chat content and do not repeat what was already covered.
- If the conversation is very short or not specific, suggest more general (but relevant) follow-ups the user might ask.
- Use the conversation's primary language; default to English if multilingual.
- Response must be a JSON object with a "follow_ups" key containing an array of strings, no extra text or formatting.
### Output:
JSON format: { "follow_ups": ["Question 1?", "Question 2?", "Question 3?"] }
### Chat History:
<chat_history>
{{MESSAGES:END:6}}
</chat_history>"""

ENABLE_FOLLOW_UP_GENERATION = PersistentConfig(
    "ENABLE_FOLLOW_UP_GENERATION",
    "task.follow_up.enable",
    os.environ.get("ENABLE_FOLLOW_UP_GENERATION", "False").lower() == "true",
)

ENABLE_TITLE_GENERATION = PersistentConfig(
    "ENABLE_TITLE_GENERATION",
    "task.title.enable",
    os.environ.get("ENABLE_TITLE_GENERATION", "False").lower() == "true",
)


ENABLE_SEARCH_QUERY_GENERATION = PersistentConfig(
    "ENABLE_SEARCH_QUERY_GENERATION",
    "task.query.search.enable",
    os.environ.get("ENABLE_SEARCH_QUERY_GENERATION", "True").lower() == "true",
)

ENABLE_RETRIEVAL_QUERY_GENERATION = PersistentConfig(
    "ENABLE_RETRIEVAL_QUERY_GENERATION",
    "task.query.retrieval.enable",
    os.environ.get("ENABLE_RETRIEVAL_QUERY_GENERATION", "True").lower() == "true",
)


QUERY_GENERATION_PROMPT_TEMPLATE = PersistentConfig(
    "QUERY_GENERATION_PROMPT_TEMPLATE",
    "task.query.prompt_template",
    os.environ.get("QUERY_GENERATION_PROMPT_TEMPLATE", ""),
)

DEFAULT_QUERY_GENERATION_PROMPT_TEMPLATE = """### Task:
Analyze the chat history to determine the necessity of generating search queries, in the given language. By default, **prioritize generating 1-3 broad and relevant search queries** unless it is absolutely certain that no additional information is required. The aim is to retrieve comprehensive, updated, and valuable information even with minimal uncertainty. If no search is unequivocally needed, return an empty list.

### Guidelines:
- Respond **EXCLUSIVELY** with a JSON object. Any form of extra commentary, explanation, or additional text is strictly prohibited.
- When generating search queries, respond in the format: { "queries": ["query1", "query2"] }, ensuring each query is distinct, concise, and relevant to the topic.
- If and only if it is entirely certain that no useful results can be retrieved by a search, return: { "queries": [] }.
- Err on the side of suggesting search queries if there is **any chance** they might provide useful or updated information.
- Be concise and focused on composing high-quality search queries, avoiding unnecessary elaboration, commentary, or assumptions.
- Today's date is: {{CURRENT_DATE}}.
- Always prioritize providing actionable and broad queries that maximize informational coverage.

### Output:
Strictly return in JSON format: 
{
  "queries": ["query1", "query2"]
}

### Chat History:
<chat_history>
{{MESSAGES:END:6}}
</chat_history>
"""

ENABLE_AUTOCOMPLETE_GENERATION = PersistentConfig(
    "ENABLE_AUTOCOMPLETE_GENERATION",
    "task.autocomplete.enable",
    os.environ.get("ENABLE_AUTOCOMPLETE_GENERATION", "False").lower() == "true",
)

AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH = PersistentConfig(
    "AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH",
    "task.autocomplete.input_max_length",
    int(os.environ.get("AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH", "-1")),
)

AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE = PersistentConfig(
    "AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE",
    "task.autocomplete.prompt_template",
    os.environ.get("AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE", ""),
)


DEFAULT_AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE = """### Task:
You are an autocompletion system. Continue the text in `<text>` based on the **completion type** in `<type>` and the given language.  

### **Instructions**:
1. Analyze `<text>` for context and meaning.  
2. Use `<type>` to guide your output:  
   - **General**: Provide a natural, concise continuation.  
   - **Search Query**: Complete as if generating a realistic search query.  
3. Start as if you are directly continuing `<text>`. Do **not** repeat, paraphrase, or respond as a model. Simply complete the text.  
4. Ensure the continuation:
   - Flows naturally from `<text>`.  
   - Avoids repetition, overexplaining, or unrelated ideas.  
5. If unsure, return: `{ "text": "" }`.  

### **Output Rules**:
- Respond only in JSON format: `{ "text": "<your_completion>" }`.

### **Examples**:
#### Example 1:  
Input:  
<type>General</type>  
<text>The sun was setting over the horizon, painting the sky</text>  
Output:  
{ "text": "with vibrant shades of orange and pink." }

#### Example 2:  
Input:  
<type>Search Query</type>  
<text>Top-rated restaurants in</text>  
Output:  
{ "text": "New York City for Italian cuisine." }  

---
### Context:
<chat_history>
{{MESSAGES:END:6}}
</chat_history>
<type>{{TYPE}}</type>  
<text>{{PROMPT}}</text>  
#### Output:
"""


VOICE_MODE_PROMPT_TEMPLATE = PersistentConfig(
    "VOICE_MODE_PROMPT_TEMPLATE",
    "task.voice.prompt_template",
    os.environ.get("VOICE_MODE_PROMPT_TEMPLATE", ""),
)

DEFAULT_VOICE_MODE_PROMPT_TEMPLATE = """You are a friendly, concise voice assistant.

Everything you say will be spoken aloud.
Keep responses short, clear, and natural.

STYLE:
- Use simple words and short sentences.
- Sound warm and conversational.
- Avoid long explanations, lists, or complex phrasing.

BEHAVIOR:
- Give the quickest helpful answer first.
- Offer extra detail only if needed.
- Ask for clarification only when necessary.

VOICE OPTIMIZATION:
- Break information into small, easy-to-hear chunks.
- Avoid dense wording or anything that sounds like reading text.

ERROR HANDLING:
- If unsure, say so briefly and offer options.
- If something is unsafe or impossible, decline kindly and suggest a safe alternative.

Stay consistent, helpful, and easy to listen to."""

TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE = PersistentConfig(
    "TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE",
    "task.tools.prompt_template",
    os.environ.get("TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE", ""),
)


DEFAULT_TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE = """Available Tools: {{TOOLS}}

Your task is to choose and return the correct tool(s) from the list of available tools based on the query. Follow these guidelines:

- Return only the JSON object, without any additional text or explanation.

- If no tools match the query, return an empty array: 
   {
     "tool_calls": []
   }

- If one or more tools match the query, construct a JSON response containing a "tool_calls" array with objects that include:
   - "name": The tool's name.
   - "parameters": A dictionary of required parameters and their corresponding values.

The format for the JSON response is strictly:
{
  "tool_calls": [
    {"name": "toolName1", "parameters": {"key1": "value1"}},
    {"name": "toolName2", "parameters": {"key2": "value2"}}
  ]
}"""


DEFAULT_EMOJI_GENERATION_PROMPT_TEMPLATE = """Your task is to reflect the speaker's likely facial expression through a fitting emoji. Interpret emotions from the message and reflect their facial expression using fitting, diverse emojis (e.g., 😊, 😢, 😡, 😱).

Message: ```{{prompt}}```"""

DEFAULT_MOA_GENERATION_PROMPT_TEMPLATE = """You have been provided with a set of responses from various models to the latest user query: "{{prompt}}"

Your task is to synthesize these responses into a single, high-quality response. It is crucial to critically evaluate the information provided in these responses, recognizing that some of it may be biased or incorrect. Your response should not simply replicate the given answers but should offer a refined, accurate, and comprehensive reply to the instruction. Ensure your response is well-structured, coherent, and adheres to the highest standards of accuracy and reliability.

Responses from models: {{responses}}"""


####################################
# Code Interpreter
####################################

ENABLE_CODE_EXECUTION = PersistentConfig(
    "ENABLE_CODE_EXECUTION",
    "code_execution.enable",
    os.environ.get("ENABLE_CODE_EXECUTION", "True").lower() == "true",
)

CODE_EXECUTION_ENGINE = PersistentConfig(
    "CODE_EXECUTION_ENGINE",
    "code_execution.engine",
    os.environ.get("CODE_EXECUTION_ENGINE", "pyodide"),
)

CODE_EXECUTION_JUPYTER_URL = PersistentConfig(
    "CODE_EXECUTION_JUPYTER_URL",
    "code_execution.jupyter.url",
    os.environ.get("CODE_EXECUTION_JUPYTER_URL", ""),
)

CODE_EXECUTION_JUPYTER_AUTH = PersistentConfig(
    "CODE_EXECUTION_JUPYTER_AUTH",
    "code_execution.jupyter.auth",
    os.environ.get("CODE_EXECUTION_JUPYTER_AUTH", ""),
)

CODE_EXECUTION_JUPYTER_AUTH_TOKEN = PersistentConfig(
    "CODE_EXECUTION_JUPYTER_AUTH_TOKEN",
    "code_execution.jupyter.auth_token",
    os.environ.get("CODE_EXECUTION_JUPYTER_AUTH_TOKEN", ""),
)


CODE_EXECUTION_JUPYTER_AUTH_PASSWORD = PersistentConfig(
    "CODE_EXECUTION_JUPYTER_AUTH_PASSWORD",
    "code_execution.jupyter.auth_password",
    os.environ.get("CODE_EXECUTION_JUPYTER_AUTH_PASSWORD", ""),
)

CODE_EXECUTION_JUPYTER_TIMEOUT = PersistentConfig(
    "CODE_EXECUTION_JUPYTER_TIMEOUT",
    "code_execution.jupyter.timeout",
    int(os.environ.get("CODE_EXECUTION_JUPYTER_TIMEOUT", "60")),
)

ENABLE_CODE_INTERPRETER = PersistentConfig(
    "ENABLE_CODE_INTERPRETER",
    "code_interpreter.enable",
    os.environ.get("ENABLE_CODE_INTERPRETER", "True").lower() == "true",
)

ENABLE_MEMORIES = PersistentConfig(
    "ENABLE_MEMORIES",
    "memories.enable",
    os.environ.get("ENABLE_MEMORIES", "True").lower() == "true",
)

CODE_INTERPRETER_ENGINE = PersistentConfig(
    "CODE_INTERPRETER_ENGINE",
    "code_interpreter.engine",
    os.environ.get("CODE_INTERPRETER_ENGINE", "pyodide"),
)

CODE_INTERPRETER_PROMPT_TEMPLATE = PersistentConfig(
    "CODE_INTERPRETER_PROMPT_TEMPLATE",
    "code_interpreter.prompt_template",
    os.environ.get("CODE_INTERPRETER_PROMPT_TEMPLATE", ""),
)

CODE_INTERPRETER_JUPYTER_URL = PersistentConfig(
    "CODE_INTERPRETER_JUPYTER_URL",
    "code_interpreter.jupyter.url",
    os.environ.get(
        "CODE_INTERPRETER_JUPYTER_URL", os.environ.get("CODE_EXECUTION_JUPYTER_URL", "")
    ),
)

CODE_INTERPRETER_JUPYTER_AUTH = PersistentConfig(
    "CODE_INTERPRETER_JUPYTER_AUTH",
    "code_interpreter.jupyter.auth",
    os.environ.get(
        "CODE_INTERPRETER_JUPYTER_AUTH",
        os.environ.get("CODE_EXECUTION_JUPYTER_AUTH", ""),
    ),
)

CODE_INTERPRETER_JUPYTER_AUTH_TOKEN = PersistentConfig(
    "CODE_INTERPRETER_JUPYTER_AUTH_TOKEN",
    "code_interpreter.jupyter.auth_token",
    os.environ.get(
        "CODE_INTERPRETER_JUPYTER_AUTH_TOKEN",
        os.environ.get("CODE_EXECUTION_JUPYTER_AUTH_TOKEN", ""),
    ),
)


CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD = PersistentConfig(
    "CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD",
    "code_interpreter.jupyter.auth_password",
    os.environ.get(
        "CODE_INTERPRETER_JUPYTER_AUTH_PASSWORD",
        os.environ.get("CODE_EXECUTION_JUPYTER_AUTH_PASSWORD", ""),
    ),
)

CODE_INTERPRETER_JUPYTER_TIMEOUT = PersistentConfig(
    "CODE_INTERPRETER_JUPYTER_TIMEOUT",
    "code_interpreter.jupyter.timeout",
    int(
        os.environ.get(
            "CODE_INTERPRETER_JUPYTER_TIMEOUT",
            os.environ.get("CODE_EXECUTION_JUPYTER_TIMEOUT", "60"),
        )
    ),
)

CODE_INTERPRETER_BLOCKED_MODULES = [
    library.strip()
    for library in os.environ.get("CODE_INTERPRETER_BLOCKED_MODULES", "").split(",")
    if library.strip()
]

DEFAULT_CODE_INTERPRETER_PROMPT = """
#### Tools Available

1. **Code Interpreter**: `<code_interpreter type="code" lang="python"></code_interpreter>`
   - You have access to a Python shell that runs directly in the user's browser, enabling fast execution of code for analysis, calculations, or problem-solving.  Use it in this response.
   - The Python code you write can incorporate a wide array of libraries, handle data manipulation or visualization, perform API calls for web-related tasks, or tackle virtually any computational challenge. Use this flexibility to **think outside the box, craft elegant solutions, and harness Python's full potential**.
   - To use it, **you must enclose your code within `<code_interpreter type="code" lang="python">` XML tags** and stop right away. If you don't, the code won't execute. 
   - When writing code in the code_interpreter XML tag, Do NOT use the triple backticks code block for markdown formatting, example: ```py # python code ``` will cause an error because it is markdown formatting, it is not python code.
   - When coding, **always aim to print meaningful outputs** (e.g., results, tables, summaries, or visuals) to better interpret and verify the findings. Avoid relying on implicit outputs; prioritize explicit and clear print statements so the results are effectively communicated to the user.  
   - After obtaining the printed output, **always provide a concise analysis, interpretation, or next steps to help the user understand the findings or refine the outcome further.**  
   - If the results are unclear, unexpected, or require validation, refine the code and execute it again as needed. Always aim to deliver meaningful insights from the results, iterating if necessary.  
   - **If a link to an image, audio, or any file is provided in markdown format in the output, ALWAYS regurgitate word for word, explicitly display it as part of the response to ensure the user can access it easily, do NOT change the link.**
   - All responses — including analysis, interpretations, print outputs and explanations — MUST be written in **Brazilian Portuguese (pt-BR)**. Never respond in English unless the user explicitly asks for it.

Ensure that the tools are effectively utilized to achieve the highest-quality analysis for the user."""

# Appended to the code interpreter prompt only when engine is pyodide (not jupyter)
CODE_INTERPRETER_PYODIDE_PROMPT = """

##### Pyodide Environment (Browser — Non-Interactive)

- This Python environment runs via **Pyodide in the browser**. There is no terminal, no keyboard, no user interaction.
- **`input()` is FORBIDDEN** — it will hang indefinitely. Never use `input()`, `sys.stdin`, `raw_input()`, or anything that reads from the user at runtime.
- **Do not install packages** — `pip install`, `subprocess`, and `micropip.install()` are not available.
- If a required library is unavailable, **rewrite the code using only available modules**. Available packages include the Python standard library plus: `numpy`, `pandas`, `matplotlib`, `scipy`, `sympy`, `PIL`, `json`, `re`, `math`, `datetime`, `collections`, `statistics`, and others bundled with Pyodide.
- If you catch yourself writing `input(`, stop and replace it with a hardcoded value.

##### Persistent File System

- User-uploaded files are available at `/mnt/uploads/`. When the user asks you to work with their files, read from this directory.
- You can also write output files to `/mnt/uploads/` so the user can access and download them.
- The file system persists across code executions within the same session.
- Use `import os; os.listdir('/mnt/uploads')` to discover available files."""


####################################
# Local Vector Database (Chroma)
####################################

VECTOR_DB = "chroma"
CHROMA_DATA_PATH = f"{DATA_DIR}/vector_db"

import chromadb

CHROMA_TENANT = chromadb.DEFAULT_TENANT
CHROMA_DATABASE = chromadb.DEFAULT_DATABASE
CHROMA_HTTP_HOST = ""
CHROMA_HTTP_PORT = 8000
CHROMA_CLIENT_AUTH_PROVIDER = ""
CHROMA_CLIENT_AUTH_CREDENTIALS = ""
CHROMA_HTTP_HEADERS = None
CHROMA_HTTP_SSL = False

####################################
# Information Retrieval (RAG)
####################################


BYPASS_EMBEDDING_AND_RETRIEVAL = PersistentConfig(
    "BYPASS_EMBEDDING_AND_RETRIEVAL",
    "rag.bypass_embedding_and_retrieval",
    os.environ.get("BYPASS_EMBEDDING_AND_RETRIEVAL", "False").lower() == "true",
)


RAG_TOP_K = PersistentConfig(
    "RAG_TOP_K", "rag.top_k", int(os.environ.get("RAG_TOP_K", "3"))
)
RAG_TOP_K_RERANKER = PersistentConfig(
    "RAG_TOP_K_RERANKER",
    "rag.top_k_reranker",
    int(os.environ.get("RAG_TOP_K_RERANKER", "3")),
)
RAG_RELEVANCE_THRESHOLD = PersistentConfig(
    "RAG_RELEVANCE_THRESHOLD",
    "rag.relevance_threshold",
    float(os.environ.get("RAG_RELEVANCE_THRESHOLD", "0.0")),
)
RAG_HYBRID_BM25_WEIGHT = PersistentConfig(
    "RAG_HYBRID_BM25_WEIGHT",
    "rag.hybrid_bm25_weight",
    float(os.environ.get("RAG_HYBRID_BM25_WEIGHT", "0.5")),
)

ENABLE_RAG_HYBRID_SEARCH = PersistentConfig(
    "ENABLE_RAG_HYBRID_SEARCH",
    "rag.enable_hybrid_search",
    os.environ.get("ENABLE_RAG_HYBRID_SEARCH", "").lower() == "true",
)

ENABLE_RAG_HYBRID_SEARCH_ENRICHED_TEXTS = PersistentConfig(
    "ENABLE_RAG_HYBRID_SEARCH_ENRICHED_TEXTS",
    "rag.enable_hybrid_search_enriched_texts",
    os.environ.get("ENABLE_RAG_HYBRID_SEARCH_ENRICHED_TEXTS", "False").lower()
    == "true",
)

RAG_FULL_CONTEXT = PersistentConfig(
    "RAG_FULL_CONTEXT",
    "rag.full_context",
    os.getenv("RAG_FULL_CONTEXT", "False").lower() == "true",
)

RAG_FILE_MAX_COUNT = PersistentConfig(
    "RAG_FILE_MAX_COUNT",
    "rag.file.max_count",
    (
        int(os.environ.get("RAG_FILE_MAX_COUNT"))
        if os.environ.get("RAG_FILE_MAX_COUNT")
        else None
    ),
)

RAG_FILE_MAX_SIZE = PersistentConfig(
    "RAG_FILE_MAX_SIZE",
    "rag.file.max_size",
    (
        int(os.environ.get("RAG_FILE_MAX_SIZE"))
        if os.environ.get("RAG_FILE_MAX_SIZE")
        else None
    ),
)

FILE_IMAGE_COMPRESSION_WIDTH = PersistentConfig(
    "FILE_IMAGE_COMPRESSION_WIDTH",
    "file.image_compression_width",
    (
        int(os.environ.get("FILE_IMAGE_COMPRESSION_WIDTH"))
        if os.environ.get("FILE_IMAGE_COMPRESSION_WIDTH")
        else None
    ),
)

FILE_IMAGE_COMPRESSION_HEIGHT = PersistentConfig(
    "FILE_IMAGE_COMPRESSION_HEIGHT",
    "file.image_compression_height",
    (
        int(os.environ.get("FILE_IMAGE_COMPRESSION_HEIGHT"))
        if os.environ.get("FILE_IMAGE_COMPRESSION_HEIGHT")
        else None
    ),
)


RAG_ALLOWED_FILE_EXTENSIONS = PersistentConfig(
    "RAG_ALLOWED_FILE_EXTENSIONS",
    "rag.file.allowed_extensions",
    [
        ext.strip()
        for ext in os.environ.get("RAG_ALLOWED_FILE_EXTENSIONS", "").split(",")
        if ext.strip()
    ],
)

PDF_EXTRACT_IMAGES = PersistentConfig(
    "PDF_EXTRACT_IMAGES",
    "rag.pdf_extract_images",
    os.environ.get("PDF_EXTRACT_IMAGES", "False").lower() == "true",
)

PDF_LOADER_MODE = PersistentConfig(
    "PDF_LOADER_MODE",
    "rag.pdf_loader_mode",
    os.environ.get("PDF_LOADER_MODE", "page"),
)

RAG_EMBEDDING_ENGINE = PersistentConfig(
    "RAG_EMBEDDING_ENGINE",
    "rag.embedding_engine",
    "",
)

RAG_EMBEDDING_MODEL = PersistentConfig(
    "RAG_EMBEDDING_MODEL",
    "rag.embedding_model",
    os.environ.get("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
)
log.info(f"Embedding model set: {RAG_EMBEDDING_MODEL.value}")

RAG_EMBEDDING_MODEL_AUTO_UPDATE = (
    not OFFLINE_MODE
    and os.environ.get("RAG_EMBEDDING_MODEL_AUTO_UPDATE", "True").lower() == "true"
)

RAG_EMBEDDING_MODEL_TRUST_REMOTE_CODE = (
    os.environ.get("RAG_EMBEDDING_MODEL_TRUST_REMOTE_CODE", "True").lower() == "true"
)

RAG_EMBEDDING_BATCH_SIZE = PersistentConfig(
    "RAG_EMBEDDING_BATCH_SIZE",
    "rag.embedding_batch_size",
    int(
        os.environ.get("RAG_EMBEDDING_BATCH_SIZE")
        or os.environ.get("RAG_EMBEDDING_OPENAI_BATCH_SIZE", "1")
    ),
)

ENABLE_ASYNC_EMBEDDING = PersistentConfig(
    "ENABLE_ASYNC_EMBEDDING",
    "rag.enable_async_embedding",
    os.environ.get("ENABLE_ASYNC_EMBEDDING", "True").lower() == "true",
)

RAG_EMBEDDING_CONCURRENT_REQUESTS = PersistentConfig(
    "RAG_EMBEDDING_CONCURRENT_REQUESTS",
    "rag.embedding_concurrent_requests",
    int(os.getenv("RAG_EMBEDDING_CONCURRENT_REQUESTS", "0")),
)

RAG_EMBEDDING_QUERY_PREFIX = os.environ.get("RAG_EMBEDDING_QUERY_PREFIX", None)

RAG_EMBEDDING_CONTENT_PREFIX = os.environ.get("RAG_EMBEDDING_CONTENT_PREFIX", None)

RAG_EMBEDDING_PREFIX_FIELD_NAME = os.environ.get(
    "RAG_EMBEDDING_PREFIX_FIELD_NAME", None
)

RAG_RERANKING_ENGINE = PersistentConfig(
    "RAG_RERANKING_ENGINE",
    "rag.reranking_engine",
    "",
)

RAG_RERANKING_MODEL = PersistentConfig(
    "RAG_RERANKING_MODEL",
    "rag.reranking_model",
    os.environ.get("RAG_RERANKING_MODEL", ""),
)
if RAG_RERANKING_MODEL.value != "":
    log.info(f"Reranking model set: {RAG_RERANKING_MODEL.value}")


RAG_RERANKING_MODEL_AUTO_UPDATE = (
    not OFFLINE_MODE
    and os.environ.get("RAG_RERANKING_MODEL_AUTO_UPDATE", "True").lower() == "true"
)

RAG_RERANKING_MODEL_TRUST_REMOTE_CODE = (
    os.environ.get("RAG_RERANKING_MODEL_TRUST_REMOTE_CODE", "True").lower() == "true"
)

RAG_TEXT_SPLITTER = PersistentConfig(
    "RAG_TEXT_SPLITTER",
    "rag.text_splitter",
    os.environ.get("RAG_TEXT_SPLITTER", ""),
)

ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER = PersistentConfig(
    "ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER",
    "rag.enable_markdown_header_text_splitter",
    os.environ.get("ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER", "True").lower() == "true",
)


TIKTOKEN_CACHE_DIR = os.environ.get("TIKTOKEN_CACHE_DIR", f"{CACHE_DIR}/tiktoken")
TIKTOKEN_ENCODING_NAME = PersistentConfig(
    "TIKTOKEN_ENCODING_NAME",
    "rag.tiktoken_encoding_name",
    os.environ.get("TIKTOKEN_ENCODING_NAME", "cl100k_base"),
)


CHUNK_SIZE = PersistentConfig(
    "CHUNK_SIZE", "rag.chunk_size", int(os.environ.get("CHUNK_SIZE", "1000"))
)

CHUNK_MIN_SIZE_TARGET = PersistentConfig(
    "CHUNK_MIN_SIZE_TARGET",
    "rag.chunk_min_size_target",
    int(os.environ.get("CHUNK_MIN_SIZE_TARGET", "0")),
)

CHUNK_OVERLAP = PersistentConfig(
    "CHUNK_OVERLAP",
    "rag.chunk_overlap",
    int(os.environ.get("CHUNK_OVERLAP", "100")),
)

DEFAULT_RAG_TEMPLATE = """### Task:
Respond to the user query using the provided context, incorporating inline citations in the format [id] **only when the <source> tag includes an explicit id attribute** (e.g., <source id="1">).

### Guidelines:
- **Provide a thorough and detailed answer.** Do not merely summarize or list titles from sources — explain the content, give specifics, details, names, numbers, and any relevant information found in the context.
- If you don't know the answer, clearly state that.
- If uncertain, ask the user for clarification.
- Respond in the same language as the user's query.
- If the context is unreadable or of poor quality, inform the user and provide the best possible answer.
- If the answer isn't present in the context but you possess the knowledge, explain this to the user and provide the answer using your own understanding. **Combine information from both the context and your own knowledge to give the most complete answer possible.**
- **Only include inline citations using [id] (e.g., [1], [2]) when the <source> tag includes an id attribute.**
- Do not cite if the <source> tag does not contain an id attribute.
- Do not use XML tags in your response.
- Ensure citations are concise and directly related to the information provided.

### Example of Citation:
If the user asks about a specific topic and the information is found in a source with a provided id attribute, the response should include the citation like in the following example:
* "According to the study, the proposed method increases efficiency by 20% [1]."

### Output:
Provide a **comprehensive, detailed, and well-structured** response to the user's query. Use all relevant information from the provided context AND your own knowledge. Include inline citations in the format [id] only when the <source> tag with id attribute is present in the context.

<context>
{{CONTEXT}}
</context>
"""

RAG_TEMPLATE = PersistentConfig(
    "RAG_TEMPLATE",
    "rag.template",
    os.environ.get("RAG_TEMPLATE", DEFAULT_RAG_TEMPLATE),
)

ENABLE_RAG_LOCAL_WEB_FETCH = (
    os.getenv("ENABLE_RAG_LOCAL_WEB_FETCH", "False").lower() == "true"
)


DEFAULT_WEB_FETCH_FILTER_LIST = [
    "!169.254.169.254",
    "!fd00:ec2::254",
    "!metadata.google.internal",
    "!metadata.azure.com",
    "!100.100.100.200",
]

web_fetch_filter_list = os.getenv("WEB_FETCH_FILTER_LIST", "")
if web_fetch_filter_list == "":
    web_fetch_filter_list = []
else:
    web_fetch_filter_list = [
        item.strip() for item in web_fetch_filter_list.split(",") if item.strip()
    ]

WEB_FETCH_FILTER_LIST = list(set(DEFAULT_WEB_FETCH_FILTER_LIST + web_fetch_filter_list))


YOUTUBE_LOADER_LANGUAGE = PersistentConfig(
    "YOUTUBE_LOADER_LANGUAGE",
    "rag.youtube_loader_language",
    os.getenv("YOUTUBE_LOADER_LANGUAGE", "en").split(","),
)

YOUTUBE_LOADER_PROXY_URL = PersistentConfig(
    "YOUTUBE_LOADER_PROXY_URL",
    "rag.youtube_loader_proxy_url",
    os.getenv("YOUTUBE_LOADER_PROXY_URL", ""),
)


####################################
# Web Search (RAG)
####################################

ENABLE_WEB_SEARCH = PersistentConfig(
    "ENABLE_WEB_SEARCH",
    "rag.web.search.enable",
    os.getenv("ENABLE_WEB_SEARCH", "True").lower() == "true",
)

WEB_SEARCH_ENGINE = PersistentConfig(
    "WEB_SEARCH_ENGINE",
    "rag.web.search.engine",
    os.getenv("WEB_SEARCH_ENGINE", "duckduckgo"),
)

BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = PersistentConfig(
    "BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL",
    "rag.web.search.bypass_embedding_and_retrieval",
    os.getenv("BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL", "False").lower() == "true",
)


BYPASS_WEB_SEARCH_WEB_LOADER = PersistentConfig(
    "BYPASS_WEB_SEARCH_WEB_LOADER",
    "rag.web.search.bypass_web_loader",
    os.getenv("BYPASS_WEB_SEARCH_WEB_LOADER", "False").lower() == "true",
)

WEB_SEARCH_RESULT_COUNT = PersistentConfig(
    "WEB_SEARCH_RESULT_COUNT",
    "rag.web.search.result_count",
    int(os.getenv("WEB_SEARCH_RESULT_COUNT", "5")),
)


try:
    web_search_domain_filter_list = json.loads(
        os.getenv("WEB_SEARCH_DOMAIN_FILTER_LIST", "[]")
    )
except Exception as e:
    web_search_domain_filter_list = [
        # "wikipedia.com",
        # "wikimedia.org",
        # "wikidata.org",
        # "!stackoverflow.com",
    ]

# You can provide a list of your own websites to filter after performing a web search.
# This ensures the highest level of safety and reliability of the information sources.
WEB_SEARCH_DOMAIN_FILTER_LIST = PersistentConfig(
    "WEB_SEARCH_DOMAIN_FILTER_LIST",
    "rag.web.search.domain.filter_list",
    web_search_domain_filter_list,
)

WEB_SEARCH_CONCURRENT_REQUESTS = PersistentConfig(
    "WEB_SEARCH_CONCURRENT_REQUESTS",
    "rag.web.search.concurrent_requests",
    int(os.getenv("WEB_SEARCH_CONCURRENT_REQUESTS", "0")),
)


WEB_LOADER_CONCURRENT_REQUESTS = PersistentConfig(
    "WEB_LOADER_CONCURRENT_REQUESTS",
    "rag.web.loader.concurrent_requests",
    int(os.getenv("WEB_LOADER_CONCURRENT_REQUESTS", "10")),
)

WEB_LOADER_TIMEOUT = PersistentConfig(
    "WEB_LOADER_TIMEOUT",
    "rag.web.loader.timeout",
    os.getenv("WEB_LOADER_TIMEOUT", ""),
)


ENABLE_WEB_LOADER_SSL_VERIFICATION = PersistentConfig(
    "ENABLE_WEB_LOADER_SSL_VERIFICATION",
    "rag.web.loader.ssl_verification",
    os.environ.get("ENABLE_WEB_LOADER_SSL_VERIFICATION", "True").lower() == "true",
)

WEB_SEARCH_TRUST_ENV = PersistentConfig(
    "WEB_SEARCH_TRUST_ENV",
    "rag.web.search.trust_env",
    os.getenv("WEB_SEARCH_TRUST_ENV", "False").lower() == "true",
)


SEARXNG_QUERY_URL = PersistentConfig(
    "SEARXNG_QUERY_URL",
    "rag.web.search.searxng_query_url",
    os.getenv("SEARXNG_QUERY_URL", ""),
)

SEARXNG_LANGUAGE = PersistentConfig(
    "SEARXNG_LANGUAGE",
    "rag.web.search.searxng_language",
    os.getenv("SEARXNG_LANGUAGE", "all"),
)

DDGS_BACKEND = PersistentConfig(
    "DDGS_BACKEND",
    "rag.web.search.ddgs_backend",
    os.getenv("DDGS_BACKEND", "auto"),
)

ENABLE_STABLE_DIFFUSION = PersistentConfig(
    "ENABLE_STABLE_DIFFUSION",
    "stable_diffusion.enable",
    os.environ.get("ENABLE_STABLE_DIFFUSION", "true").lower() == "true",
)

ENABLE_MUSIC_GENERATION = PersistentConfig(
    "ENABLE_MUSIC_GENERATION",
    "music_generation.enable",
    os.environ.get("ENABLE_MUSIC_GENERATION", "true").lower() == "true",
)

ENABLE_VIDEO_GENERATION = PersistentConfig(
    "ENABLE_VIDEO_GENERATION",
    "video_generation.enable",
    os.environ.get("ENABLE_VIDEO_GENERATION", "true").lower() == "true",
)

STABLE_DIFFUSION_MODEL = PersistentConfig(
    "STABLE_DIFFUSION_MODEL",
    "stable_diffusion.model",
    os.environ.get("STABLE_DIFFUSION_MODEL", "leejet/Z-Image-Turbo-GGUF"),
)

if str(STABLE_DIFFUSION_MODEL.value) != "leejet/Z-Image-Turbo-GGUF":
    STABLE_DIFFUSION_MODEL.value = "leejet/Z-Image-Turbo-GGUF"
    if ENABLE_PERSISTENT_CONFIG:
        STABLE_DIFFUSION_MODEL.save()

STABLE_DIFFUSION_WIDTH = PersistentConfig(
    "STABLE_DIFFUSION_WIDTH",
    "stable_diffusion.width",
    int(os.environ.get("STABLE_DIFFUSION_WIDTH", "768")),
)

STABLE_DIFFUSION_HEIGHT = PersistentConfig(
    "STABLE_DIFFUSION_HEIGHT",
    "stable_diffusion.height",
    int(os.environ.get("STABLE_DIFFUSION_HEIGHT", "768")),
)

STABLE_DIFFUSION_STEPS = PersistentConfig(
    "STABLE_DIFFUSION_STEPS",
    "stable_diffusion.steps",
    int(os.environ.get("STABLE_DIFFUSION_STEPS", "8")),
)

for _sd_config, _sd_target_value in (
    (STABLE_DIFFUSION_WIDTH, 768),
    (STABLE_DIFFUSION_HEIGHT, 768),
    (STABLE_DIFFUSION_STEPS, 8),
):
    if int(_sd_config.value) != _sd_target_value:
        _sd_config.value = _sd_target_value
        if ENABLE_PERSISTENT_CONFIG:
            _sd_config.save()

STABLE_DIFFUSION_GUIDANCE_SCALE = PersistentConfig(
    "STABLE_DIFFUSION_GUIDANCE_SCALE",
    "stable_diffusion.guidance_scale",
    float(os.environ.get("STABLE_DIFFUSION_GUIDANCE_SCALE", "1.0")),
)

if float(STABLE_DIFFUSION_GUIDANCE_SCALE.value) != 1.0:
    STABLE_DIFFUSION_GUIDANCE_SCALE.value = 1.0
    if ENABLE_PERSISTENT_CONFIG:
        STABLE_DIFFUSION_GUIDANCE_SCALE.save()

STABLE_DIFFUSION_HF_TOKEN = PersistentConfig(
    "STABLE_DIFFUSION_HF_TOKEN",
    "stable_diffusion.hf_token",
    os.environ.get(
        "STABLE_DIFFUSION_HF_TOKEN",
        os.environ.get("HUGGING_FACE_HUB_TOKEN", os.environ.get("HF_TOKEN", "")),
    ),
)

####################################
# Audio
####################################

# Transcription
WHISPER_MODEL = PersistentConfig(
    "WHISPER_MODEL",
    "audio.stt.whisper_model",
    os.getenv("WHISPER_MODEL", "base"),
)

WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_MODEL_DIR = os.getenv("WHISPER_MODEL_DIR", f"{CACHE_DIR}/whisper/models")
WHISPER_MODEL_AUTO_UPDATE = (
    not OFFLINE_MODE
    and os.environ.get("WHISPER_MODEL_AUTO_UPDATE", "").lower() == "true"
)

WHISPER_VAD_FILTER = os.getenv("WHISPER_VAD_FILTER", "False").lower() == "true"

WHISPER_MULTILINGUAL = os.getenv("WHISPER_MULTILINGUAL", "False").lower() == "true"

WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "").lower() or None

AUDIO_STT_SUPPORTED_CONTENT_TYPES = PersistentConfig(
    "AUDIO_STT_SUPPORTED_CONTENT_TYPES",
    "audio.stt.supported_content_types",
    [
        content_type.strip()
        for content_type in os.environ.get(
            "AUDIO_STT_SUPPORTED_CONTENT_TYPES", ""
        ).split(",")
        if content_type.strip()
    ],
)

AUDIO_TTS_VOICE = PersistentConfig(
    "AUDIO_TTS_VOICE",
    "audio.tts.voice",
    os.getenv("AUDIO_TTS_VOICE", "alloy"),
)

AUDIO_TTS_SPLIT_ON = PersistentConfig(
    "AUDIO_TTS_SPLIT_ON",
    "audio.tts.split_on",
    os.getenv("AUDIO_TTS_SPLIT_ON", "punctuation"),
)
