import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional, Union

import jwt
from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from neveai.constants import ERROR_MESSAGES
from neveai.env import NEVEAI_SECRET_KEY, REDIS_KEY_PREFIX
from neveai.models.auths import Auths
from neveai.models.users import Users


SESSION_SECRET = NEVEAI_SECRET_KEY
ALGORITHM = "HS256"
NO_AUTH_USER_EMAIL = "admin@localhost"
NO_AUTH_USER_NAME = "Usuario"

bearer_security = HTTPBearer(auto_error=False)


def create_token(
    data: dict, expires_delta: Union[timedelta, None] = None
) -> str:
    payload = data.copy()
    if expires_delta:
        payload["exp"] = datetime.now(UTC) + expires_delta
    payload["jti"] = str(uuid.uuid4())
    return jwt.encode(payload, SESSION_SECRET, algorithm=ALGORITHM)


def decode_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    try:
        return jwt.decode(token, SESSION_SECRET, algorithms=[ALGORITHM])
    except Exception:
        return None


async def is_valid_token(request: Request, decoded: dict) -> bool:
    if request.app.state.redis and decoded.get("jti"):
        revoked = await request.app.state.redis.get(
            f"{REDIS_KEY_PREFIX}:auth:token:{decoded['jti']}:revoked"
        )
        return not bool(revoked)
    return True


async def invalidate_token(request: Request, token: str) -> None:
    decoded = decode_token(token)
    if not decoded or not request.app.state.redis:
        return

    jti = decoded.get("jti")
    exp = decoded.get("exp")
    if jti and exp:
        ttl = exp - int(datetime.now(UTC).timestamp())
        if ttl > 0:
            await request.app.state.redis.set(
                f"{REDIS_KEY_PREFIX}:auth:token:{jti}:revoked", "1", ex=ttl
            )


def get_or_create_no_auth_user(db=None):
    user = Users.get_user_by_email(NO_AUTH_USER_EMAIL, db=db)
    if user is None:
        user = Auths.insert_new_auth(
            email=NO_AUTH_USER_EMAIL,
            password="local-no-auth",
            name=NO_AUTH_USER_NAME,
            role="admin",
            db=db,
        )
    elif user.role != "admin":
        user = Users.update_user_role_by_id(user.id, "admin", db=db) or user

    if user is None:
        raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)
    return user


def get_http_authorization_cred(
    auth_header: Optional[str],
) -> Optional[HTTPAuthorizationCredentials]:
    if not auth_header:
        return None
    try:
        scheme, credentials = auth_header.split(" ", 1)
        return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
    except ValueError:
        return None


async def get_current_user(
    request: Request,
    background_tasks: BackgroundTasks,
    auth_token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_security),
):
    token = auth_token.credentials if auth_token else request.cookies.get("token")
    decoded = decode_token(token)
    user = None

    if decoded and "id" in decoded and await is_valid_token(request, decoded):
        user = Users.get_user_by_id(decoded["id"])

    if user is None:
        user = get_or_create_no_auth_user()

    if background_tasks:
        background_tasks.add_task(Users.update_last_active_by_id, user.id)
    return user


def get_verified_user(user=Depends(get_current_user)):
    if user.role not in {"user", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    return user


def get_admin_user(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    return user
