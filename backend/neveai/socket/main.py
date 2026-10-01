import asyncio
import random

import socketio
import logging
import sys
import time
from typing import Dict, Set
from redis import asyncio as aioredis

from neveai.models.users import Users
from neveai.models.chats import Chats
from neveai.utils.redis import (
    get_sentinels_from_env,
    get_sentinel_url_from_env,
)

from neveai.config import (
    CORS_ALLOW_ORIGIN,
)

from neveai.env import (
    VERSION,
    ENABLE_WEBSOCKET_SUPPORT,
    WEBSOCKET_MANAGER,
    WEBSOCKET_REDIS_URL,
    WEBSOCKET_REDIS_CLUSTER,
    WEBSOCKET_REDIS_LOCK_TIMEOUT,
    WEBSOCKET_SENTINEL_PORT,
    WEBSOCKET_SENTINEL_HOSTS,
    REDIS_KEY_PREFIX,
    WEBSOCKET_REDIS_OPTIONS,
    WEBSOCKET_SERVER_PING_TIMEOUT,
    WEBSOCKET_SERVER_PING_INTERVAL,
    WEBSOCKET_SERVER_LOGGING,
    WEBSOCKET_SERVER_ENGINEIO_LOGGING,
    WEBSOCKET_EVENT_CALLER_TIMEOUT,
)
from neveai.utils.auth import decode_token
from neveai.socket.utils import RedisDict, RedisLock
from neveai.utils.redis import get_redis_connection


from neveai.env import (
    GLOBAL_LOG_LEVEL,
)

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)


REDIS = None

# Configure CORS for Socket.IO
SOCKETIO_CORS_ORIGINS = "*" if CORS_ALLOW_ORIGIN == ["*"] else CORS_ALLOW_ORIGIN

if WEBSOCKET_MANAGER == "redis":
    if WEBSOCKET_SENTINEL_HOSTS:
        mgr = socketio.AsyncRedisManager(
            get_sentinel_url_from_env(
                WEBSOCKET_REDIS_URL, WEBSOCKET_SENTINEL_HOSTS, WEBSOCKET_SENTINEL_PORT
            ),
            redis_options=WEBSOCKET_REDIS_OPTIONS,
        )
    else:
        mgr = socketio.AsyncRedisManager(
            WEBSOCKET_REDIS_URL, redis_options=WEBSOCKET_REDIS_OPTIONS
        )
    sio = socketio.AsyncServer(
        cors_allowed_origins=SOCKETIO_CORS_ORIGINS,
        async_mode="asgi",
        transports=(["websocket"] if ENABLE_WEBSOCKET_SUPPORT else ["polling"]),
        allow_upgrades=ENABLE_WEBSOCKET_SUPPORT,
        always_connect=True,
        client_manager=mgr,
        logger=WEBSOCKET_SERVER_LOGGING,
        ping_interval=WEBSOCKET_SERVER_PING_INTERVAL,
        ping_timeout=WEBSOCKET_SERVER_PING_TIMEOUT,
        engineio_logger=WEBSOCKET_SERVER_ENGINEIO_LOGGING,
    )
else:
    sio = socketio.AsyncServer(
        cors_allowed_origins=SOCKETIO_CORS_ORIGINS,
        async_mode="asgi",
        transports=(["websocket"] if ENABLE_WEBSOCKET_SUPPORT else ["polling"]),
        allow_upgrades=ENABLE_WEBSOCKET_SUPPORT,
        always_connect=True,
        logger=WEBSOCKET_SERVER_LOGGING,
        ping_interval=WEBSOCKET_SERVER_PING_INTERVAL,
        ping_timeout=WEBSOCKET_SERVER_PING_TIMEOUT,
        engineio_logger=WEBSOCKET_SERVER_ENGINEIO_LOGGING,
    )


# Timeout duration in seconds
TIMEOUT_DURATION = 3
SESSION_POOL_TIMEOUT = 120  # seconds without heartbeat before session is reaped

# Dictionary to maintain the user pool

if WEBSOCKET_MANAGER == "redis":
    log.debug("Using Redis to manage websockets.")
    REDIS = get_redis_connection(
        redis_url=WEBSOCKET_REDIS_URL,
        redis_sentinels=get_sentinels_from_env(
            WEBSOCKET_SENTINEL_HOSTS, WEBSOCKET_SENTINEL_PORT
        ),
        redis_cluster=WEBSOCKET_REDIS_CLUSTER,
        async_mode=True,
    )

    redis_sentinels = get_sentinels_from_env(
        WEBSOCKET_SENTINEL_HOSTS, WEBSOCKET_SENTINEL_PORT
    )

    MODELS = RedisDict(
        f"{REDIS_KEY_PREFIX}:models",
        redis_url=WEBSOCKET_REDIS_URL,
        redis_sentinels=redis_sentinels,
        redis_cluster=WEBSOCKET_REDIS_CLUSTER,
    )

    SESSION_POOL = RedisDict(
        f"{REDIS_KEY_PREFIX}:session_pool",
        redis_url=WEBSOCKET_REDIS_URL,
        redis_sentinels=redis_sentinels,
        redis_cluster=WEBSOCKET_REDIS_CLUSTER,
    )
    USAGE_POOL = RedisDict(
        f"{REDIS_KEY_PREFIX}:usage_pool",
        redis_url=WEBSOCKET_REDIS_URL,
        redis_sentinels=redis_sentinels,
        redis_cluster=WEBSOCKET_REDIS_CLUSTER,
    )

    clean_up_lock = RedisLock(
        redis_url=WEBSOCKET_REDIS_URL,
        lock_name=f"{REDIS_KEY_PREFIX}:usage_cleanup_lock",
        timeout_secs=WEBSOCKET_REDIS_LOCK_TIMEOUT,
        redis_sentinels=redis_sentinels,
        redis_cluster=WEBSOCKET_REDIS_CLUSTER,
    )
    aquire_func = clean_up_lock.aquire_lock
    renew_func = clean_up_lock.renew_lock
    release_func = clean_up_lock.release_lock

    session_cleanup_lock = RedisLock(
        redis_url=WEBSOCKET_REDIS_URL,
        lock_name=f"{REDIS_KEY_PREFIX}:session_cleanup_lock",
        timeout_secs=WEBSOCKET_REDIS_LOCK_TIMEOUT,
        redis_sentinels=redis_sentinels,
        redis_cluster=WEBSOCKET_REDIS_CLUSTER,
    )
    session_aquire_func = session_cleanup_lock.aquire_lock
    session_renew_func = session_cleanup_lock.renew_lock
    session_release_func = session_cleanup_lock.release_lock
else:
    MODELS = {}

    SESSION_POOL = {}
    USAGE_POOL = {}

    aquire_func = release_func = renew_func = lambda: True
    session_aquire_func = session_release_func = session_renew_func = lambda: True


async def periodic_session_pool_cleanup():
    """Reap orphaned SESSION_POOL entries that missed heartbeats (e.g. crashed instance)."""
    if not session_aquire_func():
        log.debug("Session cleanup lock held by another node. Skipping.")
        return

    try:
        while True:
            if not session_renew_func():
                log.error("Unable to renew session cleanup lock. Exiting.")
                return

            now = int(time.time())
            for sid in list(SESSION_POOL.keys()):
                entry = SESSION_POOL.get(sid)
                if entry and now - entry.get("last_seen_at", 0) > SESSION_POOL_TIMEOUT:
                    log.warning(
                        f"Reaping orphaned session {sid} (user {entry.get('id')})"
                    )
                    del SESSION_POOL[sid]
            await asyncio.sleep(SESSION_POOL_TIMEOUT)
    finally:
        session_release_func()


async def periodic_usage_pool_cleanup():
    max_retries = 2
    retry_delay = random.uniform(
        WEBSOCKET_REDIS_LOCK_TIMEOUT / 2, WEBSOCKET_REDIS_LOCK_TIMEOUT
    )
    for attempt in range(max_retries + 1):
        if aquire_func():
            break
        else:
            if attempt < max_retries:
                log.debug(
                    f"Cleanup lock already exists. Retry {attempt + 1} after {retry_delay}s..."
                )
                await asyncio.sleep(retry_delay)
            else:
                log.warning(
                    "Failed to acquire cleanup lock after retries. Skipping cleanup."
                )
                return

    log.debug("Running periodic_cleanup")
    try:
        while True:
            if not renew_func():
                log.error(f"Unable to renew cleanup lock. Exiting usage pool cleanup.")
                raise Exception("Unable to renew usage pool cleanup lock.")

            now = int(time.time())
            send_usage = False
            for model_id, connections in list(USAGE_POOL.items()):
                # Creating a list of sids to remove if they have timed out
                expired_sids = [
                    sid
                    for sid, details in connections.items()
                    if now - details["updated_at"] > TIMEOUT_DURATION
                ]

                for sid in expired_sids:
                    del connections[sid]

                if not connections:
                    log.debug(f"Cleaning up model {model_id} from usage pool")
                    del USAGE_POOL[model_id]
                else:
                    USAGE_POOL[model_id] = connections

                send_usage = True
            await asyncio.sleep(TIMEOUT_DURATION)
    finally:
        release_func()


app = socketio.ASGIApp(
    sio,
    socketio_path="/ws/socket.io",
)


def get_models_in_use():
    # List models that are currently in use
    models_in_use = list(USAGE_POOL.keys())
    return models_in_use


def get_user_id_from_session_pool(sid):
    user = SESSION_POOL.get(sid)
    if user:
        return user["id"]
    return None


def get_session_ids_from_room(room):
    """Get all session IDs from a specific room."""
    active_session_ids = sio.manager.get_participants(
        namespace="/",
        room=room,
    )
    return [session_id[0] for session_id in active_session_ids]


def get_user_ids_from_room(room):
    active_session_ids = get_session_ids_from_room(room)

    active_user_ids = list(
        set(
            [
                SESSION_POOL.get(session_id)["id"]
                for session_id in active_session_ids
                if SESSION_POOL.get(session_id) is not None
            ]
        )
    )
    return active_user_ids


async def emit_to_users(event: str, data: dict, user_ids: list[str]):
    """
    Send a message to specific users using their user:{id} rooms.

    Args:
        event (str): The event name to emit.
        data (dict): The payload/data to send.
        user_ids (list[str]): The target users' IDs.
    """
    try:
        for user_id in user_ids:
            await sio.emit(event, data, room=f"user:{user_id}")
    except Exception as e:
        log.debug(f"Failed to emit event {event} to users {user_ids}: {e}")


async def enter_room_for_users(room: str, user_ids: list[str]):
    """
    Make all sessions of a user join a specific room.
    Args:
        room (str): The room to join.
        user_ids (list[str]): The target user's IDs.
    """
    try:
        for user_id in user_ids:
            session_ids = get_session_ids_from_room(f"user:{user_id}")
            for sid in session_ids:
                await sio.enter_room(sid, room)
    except Exception as e:
        log.debug(f"Failed to make users {user_ids} join room {room}: {e}")


@sio.on("usage")
async def usage(sid, data):
    if sid in SESSION_POOL:
        model_id = data["model"]
        # Record the timestamp for the last update
        current_time = int(time.time())

        # Store the new usage data and task
        USAGE_POOL[model_id] = {
            **(USAGE_POOL[model_id] if model_id in USAGE_POOL else {}),
            sid: {"updated_at": current_time},
        }


@sio.event
async def connect(sid, environ, auth):
    user = None
    if auth and "token" in auth:
        data = decode_token(auth["token"])

        if data is not None and "id" in data:
            user = Users.get_user_by_id(data["id"])

        if user:
            SESSION_POOL[sid] = {
                **user.model_dump(
                    exclude=[
                        "profile_image_url",
                        "profile_banner_image_url",
                        "date_of_birth",
                        "bio",
                        "gender",
                    ]
                ),
                "last_seen_at": int(time.time()),
            }
            await sio.enter_room(sid, f"user:{user.id}")


@sio.on("user-join")
async def user_join(sid, data):

    auth = data["auth"] if "auth" in data else None
    if not auth or "token" not in auth:
        return

    data = decode_token(auth["token"])
    if data is None or "id" not in data:
        return

    user = Users.get_user_by_id(data["id"])
    if not user:
        return

    SESSION_POOL[sid] = {
        **user.model_dump(
            exclude=[
                "profile_image_url",
                "profile_banner_image_url",
                "date_of_birth",
                "bio",
                "gender",
            ]
        ),
        "last_seen_at": int(time.time()),
    }

    await sio.enter_room(sid, f"user:{user.id}")

    return {"id": user.id, "name": user.name}


@sio.on("heartbeat")
async def heartbeat(sid, data):
    user = SESSION_POOL.get(sid)
    if user:
        SESSION_POOL[sid] = {**user, "last_seen_at": int(time.time())}
        Users.update_last_active_by_id(user["id"])


@sio.event
async def disconnect(sid):
    if sid in SESSION_POOL:
        user = SESSION_POOL[sid]
        del SESSION_POOL[sid]

        # Clean up USAGE_POOL entries for this session
        for model_id in list(USAGE_POOL.keys()):
            connections = USAGE_POOL.get(model_id)
            if connections and sid in connections:
                del connections[sid]
                if not connections:
                    del USAGE_POOL[model_id]
                else:
                    USAGE_POOL[model_id] = connections

    else:
        pass
        # print(f"Unknown session ID {sid} disconnected")


def get_event_emitter(request_info, update_db=True):
    async def __event_emitter__(event_data):
        user_id = request_info["user_id"]
        chat_id = request_info["chat_id"]
        message_id = request_info["message_id"]

        await sio.emit(
            "events",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "data": event_data,
            },
            room=f"user:{user_id}",
        )

        if (
            update_db
            and message_id
            and not request_info.get("chat_id", "").startswith("local:")
        ):

            event_type = event_data.get("type")

            if event_type == "status":
                await asyncio.to_thread(
                    Chats.add_message_status_to_chat_by_id_and_message_id,
                    request_info["chat_id"],
                    request_info["message_id"],
                    event_data.get("data", {}),
                )

            elif event_type == "message":
                message = await asyncio.to_thread(
                    Chats.get_message_by_id_and_message_id,
                    request_info["chat_id"],
                    request_info["message_id"],
                )

                if message:
                    content = message.get("content", "")
                    content += event_data.get("data", {}).get("content", "")

                    await asyncio.to_thread(
                        Chats.upsert_message_to_chat_by_id_and_message_id,
                        request_info["chat_id"],
                        request_info["message_id"],
                        {
                            "content": content,
                        },
                    )

            elif event_type == "replace":
                content = event_data.get("data", {}).get("content", "")

                await asyncio.to_thread(
                    Chats.upsert_message_to_chat_by_id_and_message_id,
                    request_info["chat_id"],
                    request_info["message_id"],
                    {
                        "content": content,
                    },
                )

            elif event_type == "embeds":
                message = await asyncio.to_thread(
                    Chats.get_message_by_id_and_message_id,
                    request_info["chat_id"],
                    request_info["message_id"],
                )

                embeds = event_data.get("data", {}).get("embeds", [])
                embeds.extend(message.get("embeds", []))

                await asyncio.to_thread(
                    Chats.upsert_message_to_chat_by_id_and_message_id,
                    request_info["chat_id"],
                    request_info["message_id"],
                    {
                        "embeds": embeds,
                    },
                )

            elif event_type == "files":
                message = await asyncio.to_thread(
                    Chats.get_message_by_id_and_message_id,
                    request_info["chat_id"],
                    request_info["message_id"],
                )

                files = event_data.get("data", {}).get("files", [])
                files.extend(message.get("files", []))

                await asyncio.to_thread(
                    Chats.upsert_message_to_chat_by_id_and_message_id,
                    request_info["chat_id"],
                    request_info["message_id"],
                    {
                        "files": files,
                    },
                )

            elif event_type in ("source", "citation"):
                data = event_data.get("data", {})
                if data.get("type") is None:
                    message = await asyncio.to_thread(
                        Chats.get_message_by_id_and_message_id,
                        request_info["chat_id"],
                        request_info["message_id"],
                    )

                    sources = message.get("sources", [])
                    sources.append(data)

                    await asyncio.to_thread(
                        Chats.upsert_message_to_chat_by_id_and_message_id,
                        request_info["chat_id"],
                        request_info["message_id"],
                        {
                            "sources": sources,
                        },
                    )

    if (
        "user_id" in request_info
        and "chat_id" in request_info
        and "message_id" in request_info
    ):
        return __event_emitter__
    else:
        return None


def get_event_call(request_info):
    async def __event_caller__(event_data):
        response = await sio.call(
            "events",
            {
                "chat_id": request_info.get("chat_id", None),
                "message_id": request_info.get("message_id", None),
                "data": event_data,
            },
            to=request_info["session_id"],
            timeout=WEBSOCKET_EVENT_CALLER_TIMEOUT,
        )
        return response

    if (
        "session_id" in request_info
        and "chat_id" in request_info
        and "message_id" in request_info
    ):
        return __event_caller__
    else:
        return None


get_event_caller = get_event_call
