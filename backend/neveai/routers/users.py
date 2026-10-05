import base64
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from neveai.constants import ERROR_MESSAGES
from neveai.env import STATIC_DIR
from neveai.internal.db import get_session
from neveai.models.users import (
    UserSettings,
    Users,
)
from neveai.utils.auth import get_verified_user


router = APIRouter()
PAGE_ITEM_COUNT = 30


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
