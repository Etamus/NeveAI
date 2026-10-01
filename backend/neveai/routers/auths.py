import datetime
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from neveai.constants import ERROR_MESSAGES
from neveai.env import NEVEAI_AUTH_COOKIE_SAME_SITE, NEVEAI_AUTH_COOKIE_SECURE
from neveai.internal.db import get_session
from neveai.models.auths import Token
from neveai.models.users import (
    UpdateProfileForm,
    UserProfileImageResponse,
    Users,
    UserStatus,
)
from neveai.utils.access_control import get_permissions
from neveai.utils.auth import (
    create_token,
    decode_token,
    get_current_user,
    get_http_authorization_cred,
    get_or_create_no_auth_user,
    get_verified_user,
    invalidate_token,
)
from neveai.utils.misc import parse_duration


router = APIRouter()


class SessionUserResponse(Token, UserProfileImageResponse):
    expires_at: Optional[int] = None
    permissions: Optional[dict] = None


class SessionUserInfoResponse(SessionUserResponse, UserStatus):
    bio: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[datetime.date] = None


def create_session_response(
    request: Request,
    user,
    db: Session,
    response: Optional[Response] = None,
    set_cookie: bool = False,
) -> dict:
    expires_delta = parse_duration(request.app.state.config.JWT_EXPIRES_IN)
    expires_at = (
        int(time.time()) + int(expires_delta.total_seconds())
        if expires_delta
        else None
    )
    token = create_token(data={"id": user.id}, expires_delta=expires_delta)

    if set_cookie and response:
        response.set_cookie(
            key="token",
            value=token,
            expires=(
                datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc)
                if expires_at
                else None
            ),
            httponly=True,
            samesite=NEVEAI_AUTH_COOKIE_SAME_SITE,
            secure=NEVEAI_AUTH_COOKIE_SECURE,
        )

    return {
        "token": token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": "admin",
        "profile_image_url": user.profile_image_url
        or f"/api/v1/users/{user.id}/profile/image",
        "permissions": get_permissions(
            user.id, request.app.state.config.USER_PERMISSIONS, db=db
        ),
    }


def create_session_user_payload(request: Request, user, db: Session) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": "admin",
        "profile_image_url": user.profile_image_url
        or f"/api/v1/users/{user.id}/profile/image",
        "permissions": get_permissions(
            user.id, request.app.state.config.USER_PERMISSIONS, db=db
        ),
    }


@router.get("/", response_model=SessionUserInfoResponse)
async def get_session_user(
    request: Request,
    response: Response,
    user=Depends(get_current_user),
    db: Session = Depends(get_session),
):
    auth_header = request.headers.get("Authorization")
    auth_token = get_http_authorization_cred(auth_header)
    token = auth_token.credentials if auth_token else request.cookies.get("token")
    data = decode_token(token) if token else None

    if not data or (data.get("exp") and int(time.time()) > data["exp"]):
        return create_session_response(request, user, db, response, set_cookie=True)

    response.set_cookie(
        key="token",
        value=token,
        expires=(
            datetime.datetime.fromtimestamp(data["exp"], datetime.timezone.utc)
            if data.get("exp")
            else None
        ),
        httponly=True,
        samesite=NEVEAI_AUTH_COOKIE_SAME_SITE,
        secure=NEVEAI_AUTH_COOKIE_SECURE,
    )
    return {
        **create_session_user_payload(request, user, db),
        "token": token,
        "token_type": "Bearer",
        "expires_at": data.get("exp"),
        "profile_image_url": user.profile_image_url,
        "bio": user.bio,
        "gender": user.gender,
        "date_of_birth": user.date_of_birth,
        "status_emoji": user.status_emoji,
        "status_message": user.status_message,
        "status_expires_at": user.status_expires_at,
    }


@router.post("/noauth", response_model=SessionUserResponse)
async def noauth(
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
):
    user = get_or_create_no_auth_user(db=db)
    return create_session_response(request, user, db, response, set_cookie=True)


@router.post("/update/profile", response_model=UserProfileImageResponse)
async def update_profile(
    form_data: UpdateProfileForm,
    session_user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    user = Users.update_user_by_id(
        session_user.id, form_data.model_dump(), db=db
    )
    if not user:
        raise HTTPException(400, detail=ERROR_MESSAGES.DEFAULT())
    return user


@router.get("/signout")
async def signout(request: Request, response: Response):
    auth_header = request.headers.get("Authorization")
    auth_cred = get_http_authorization_cred(auth_header) if auth_header else None
    token = auth_cred.credentials if auth_cred else request.cookies.get("token")
    if token:
        await invalidate_token(request, token)

    response.delete_cookie("token")
    response.delete_cookie("oui-session")
    return JSONResponse(
        status_code=200,
        content={"status": True},
        headers=response.headers,
    )
