import base64
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from neveai.constants import ERROR_MESSAGES
from neveai.env import STATIC_DIR
from neveai.internal.db import get_session
from neveai.models.groups import Groups
from neveai.models.users import (
    UserInfoListResponse,
    UserInfoResponse,
    UserSettings,
    Users,
)
from neveai.utils.access_control import has_permission
from neveai.utils.auth import get_verified_user


router = APIRouter()
PAGE_ITEM_COUNT = 30


@router.get("/search", response_model=UserInfoListResponse)
async def search_users(
    query: Optional[str] = None,
    order_by: Optional[str] = None,
    direction: Optional[str] = None,
    page: int = 1,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    filters = {}
    if query:
        filters["query"] = query
    if order_by:
        filters["order_by"] = order_by
    if direction:
        filters["direction"] = direction
    return Users.get_users(
        filter=filters,
        skip=(max(1, page) - 1) * PAGE_ITEM_COUNT,
        limit=PAGE_ITEM_COUNT,
        db=db,
    )


@router.get("/user/settings", response_model=Optional[UserSettings])
async def get_user_settings(
    user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    current = Users.get_user_by_id(user.id, db=db)
    if not current:
        raise HTTPException(400, detail=ERROR_MESSAGES.USER_NOT_FOUND)
    return current.settings


@router.post("/user/settings/update", response_model=UserSettings)
async def update_user_settings(
    request: Request,
    form_data: UserSettings,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    settings = form_data.model_dump()
    ui_settings = settings.get("ui")
    if (
        user.role != "admin"
        and ui_settings is not None
        and "toolServers" in ui_settings
        and not has_permission(
            user.id,
            "features.direct_tool_servers",
            request.app.state.config.USER_PERMISSIONS,
        )
    ):
        ui_settings.pop("toolServers", None)

    current = Users.update_user_settings_by_id(user.id, settings, db=db)
    if not current:
        raise HTTPException(400, detail=ERROR_MESSAGES.USER_NOT_FOUND)
    return current.settings


@router.post("/user/info/update", response_model=Optional[dict])
async def update_user_info(
    form_data: dict,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    current = Users.get_user_by_id(user.id, db=db)
    if not current:
        raise HTTPException(400, detail=ERROR_MESSAGES.USER_NOT_FOUND)
    updated = Users.update_user_by_id(
        user.id, {"info": {**(current.info or {}), **form_data}}, db=db
    )
    if not updated:
        raise HTTPException(400, detail=ERROR_MESSAGES.USER_NOT_FOUND)
    return updated.info


@router.get("/{user_id}/info", response_model=UserInfoResponse)
async def get_user_info(
    user_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    target = Users.get_user_by_id(user_id, db=db)
    if not target:
        raise HTTPException(400, detail=ERROR_MESSAGES.USER_NOT_FOUND)
    groups = Groups.get_groups_by_member_id(user_id, db=db)
    return UserInfoResponse(
        **target.model_dump(),
        groups=[{"id": group.id, "name": group.name} for group in groups],
        is_active=Users.is_user_active(user_id, db=db),
    )


@router.get("/{user_id}/profile/image")
def get_user_profile_image(
    user_id: str, user=Depends(get_verified_user)
):
    target = Users.get_user_by_id(user_id)
    if not target:
        raise HTTPException(400, detail=ERROR_MESSAGES.USER_NOT_FOUND)

    image_url = target.profile_image_url or ""
    if image_url.startswith("http"):
        return Response(status_code=status.HTTP_302_FOUND, headers={"Location": image_url})
    if image_url.startswith("data:image"):
        try:
            header, encoded = image_url.split(",", 1)
            return StreamingResponse(
                io.BytesIO(base64.b64decode(encoded)),
                media_type=header.split(";")[0].removeprefix("data:"),
                headers={"Content-Disposition": "inline"},
            )
        except (ValueError, TypeError):
            pass
    return FileResponse(f"{STATIC_DIR}/user.png")
