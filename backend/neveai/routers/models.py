from typing import Optional
import io
import base64
import json
import asyncio
import logging
import time
from pathlib import Path

from neveai.models.groups import Groups
from neveai.models.models import (
    ModelForm,
    ModelMeta,
    ModelModel,
    ModelParams,
    ModelResponse,
    ModelListResponse,
    ModelAccessListResponse,
    ModelAccessResponse,
    Models,
)
from neveai.models.access_grants import AccessGrants
from neveai.routers import llamacpp
from neveai.utils.model_defaults import (
    get_effective_model_metadata,
    get_effective_model_params,
    mark_model_form_user_customized,
    model_has_user_edits,
)

from pydantic import BaseModel
from neveai.constants import ERROR_MESSAGES
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
    Response,
)
from fastapi.responses import FileResponse, StreamingResponse


from neveai.utils.auth import get_admin_user, get_verified_user
from neveai.utils.access_control import has_permission, filter_allowed_access_grants
from neveai.config import BYPASS_ADMIN_ACCESS_CONTROL, STATIC_DIR
from neveai.internal.db import get_session
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

router = APIRouter()


def is_valid_model_id(model_id: str) -> bool:
    return model_id and len(model_id) <= 256


def get_local_base_model_by_id(model_id: str) -> Optional[dict]:
    if not model_id.startswith("local/"):
        return None

    for model in llamacpp.model_manager.scan_models():
        if model.get("id") == model_id:
            return model

    return None


def local_model_display_name(model: dict) -> str:
    return (
        model.get("filename", "")
        .replace(".gguf", "")
        .replace("-", " ")
        .replace("_", " ")
        .title()
    )


def get_static_profile_image_response(profile_image_url: str, etag: Optional[str] = None):
    if not profile_image_url:
        return None

    if profile_image_url.startswith("/static/"):
        relative_path = profile_image_url.removeprefix("/static/")
    elif profile_image_url.startswith("static/"):
        relative_path = profile_image_url.removeprefix("static/")
    else:
        return None

    static_root = Path(STATIC_DIR).resolve()
    image_path = (static_root / relative_path).resolve()

    try:
        image_path.relative_to(static_root)
    except ValueError:
        return None

    if not image_path.is_file():
        return None

    headers = {"Content-Disposition": "inline", "Cache-Control": "no-cache"}
    if etag:
        headers["ETag"] = etag

    return FileResponse(image_path, headers=headers)


def lock_neve_catalog_profile_image(model: ModelModel, form_data: ModelForm) -> ModelForm:
    existing_meta = model.meta.model_dump() if model.meta else {}
    catalog_profile_image_url = llamacpp.get_catalog_profile_image_url(existing_meta)
    if not catalog_profile_image_url:
        return form_data

    form_model_data = form_data.model_dump()
    form_meta = form_model_data.get("meta") or {}
    form_meta["profile_image_url"] = catalog_profile_image_url
    form_meta["neve_catalog_id"] = existing_meta.get("neve_catalog_id")
    form_meta["neve_catalog_profile_image_locked"] = True

    if existing_meta.get("neve_catalog_repo"):
        form_meta["neve_catalog_repo"] = existing_meta.get("neve_catalog_repo")
    if existing_meta.get("neve_catalog_defaults_version"):
        form_meta["neve_catalog_defaults_version"] = existing_meta.get(
            "neve_catalog_defaults_version"
        )

    form_model_data["meta"] = form_meta
    return ModelForm(**form_model_data)


def build_model_response_with_defaults(
    request: Request, model: ModelModel, write_access: bool
) -> ModelAccessResponse:
    default_params = getattr(request.app.state.config, "DEFAULT_MODEL_PARAMS", None) or {}
    default_metadata = getattr(request.app.state.config, "DEFAULT_MODEL_METADATA", None) or {}
    user_customized = model_has_user_edits(model)

    model_data = model.model_dump()
    model_data["params"] = get_effective_model_params(model, default_params)
    model_data["meta"] = get_effective_model_metadata(
        model_data.get("meta"), default_metadata, user_customized=user_customized
    )

    return ModelAccessResponse(**model_data, write_access=write_access)


###########################
# GetModels
###########################


PAGE_ITEM_COUNT = 30


@router.get(
    "/list", response_model=ModelAccessListResponse
)  # do NOT use "/" as path, conflicts with main.py
async def get_models(
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    tag: Optional[str] = None,
    order_by: Optional[str] = None,
    direction: Optional[str] = None,
    page: Optional[int] = 1,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):

    limit = PAGE_ITEM_COUNT

    page = max(1, page)
    skip = (page - 1) * limit

    filter = {}
    if query:
        filter["query"] = query
    if view_option:
        filter["view_option"] = view_option
    if tag:
        filter["tag"] = tag
    if order_by:
        filter["order_by"] = order_by
    if direction:
        filter["direction"] = direction

    # Pre-fetch user group IDs once - used for both filter and write_access check
    groups = Groups.get_groups_by_member_id(user.id, db=db)
    user_group_ids = {group.id for group in groups}

    if not user.role == "admin" or not BYPASS_ADMIN_ACCESS_CONTROL:
        if groups:
            filter["group_ids"] = [group.id for group in groups]

        filter["user_id"] = user.id

    result = Models.search_models(user.id, filter=filter, skip=skip, limit=limit, db=db)

    # Batch-fetch writable model IDs in a single query instead of N has_access calls
    model_ids = [model.id for model in result.items]
    writable_model_ids = AccessGrants.get_accessible_resource_ids(
        user_id=user.id,
        resource_type="model",
        resource_ids=model_ids,
        permission="write",
        user_group_ids=user_group_ids,
        db=db,
    )

    return ModelAccessListResponse(
        items=[
            ModelAccessResponse(
                **model.model_dump(),
                write_access=(
                    (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or user.id == model.user_id
                    or model.id in writable_model_ids
                ),
            )
            for model in result.items
        ],
        total=result.total,
    )


###########################
# GetBaseModels
###########################


@router.get("/base", response_model=list[ModelResponse])
async def get_base_models(
    user=Depends(get_admin_user), db: Session = Depends(get_session)
):
    return Models.get_base_models(db=db)


###########################
# GetModelTags
###########################


@router.get("/tags", response_model=list[str])
async def get_model_tags(
    user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        models = Models.get_models(db=db)
    else:
        models = Models.get_models_by_user_id(user.id, db=db)

    tags_set = set()
    for model in models:
        if model.meta:
            meta = model.meta.model_dump()
            for tag in meta.get("tags", []):
                tags_set.add((tag.get("name")))

    tags = [tag for tag in tags_set]
    tags.sort()
    return tags


############################
# CreateNewModel
############################


@router.post("/create", response_model=Optional[ModelModel])
async def create_new_model(
    request: Request,
    form_data: ModelForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    if user.role != "admin" and not has_permission(
        user.id, "workspace.models", request.app.state.config.USER_PERMISSIONS, db=db
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    model = Models.get_model_by_id(form_data.id, db=db)
    if model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.MODEL_ID_TAKEN,
        )

    if not is_valid_model_id(form_data.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.MODEL_ID_TOO_LONG,
        )

    else:
        model = Models.insert_new_model(form_data, user.id, db=db)
        if model:
            return model
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.DEFAULT(),
            )


############################
# ExportModels
############################


@router.get("/export", response_model=list[ModelModel])
async def export_models(
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    if user.role != "admin" and not has_permission(
        user.id,
        "workspace.models_export",
        request.app.state.config.USER_PERMISSIONS,
        db=db,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        return Models.get_models(db=db)
    else:
        return Models.get_models_by_user_id(user.id, db=db)


############################
# ImportModels
############################


class ModelsImportForm(BaseModel):
    models: list[dict]


@router.post("/import", response_model=bool)
async def import_models(
    request: Request,
    user=Depends(get_verified_user),
    form_data: ModelsImportForm = (...),
    db: Session = Depends(get_session),
):
    if user.role != "admin" and not has_permission(
        user.id,
        "workspace.models_import",
        request.app.state.config.USER_PERMISSIONS,
        db=db,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )
    try:
        data = form_data.models
        if isinstance(data, list):
            # Batch-fetch all existing models in one query to avoid N+1
            model_ids = [
                model_data.get("id")
                for model_data in data
                if model_data.get("id") and is_valid_model_id(model_data.get("id"))
            ]
            existing_models = {
                model.id: model
                for model in (
                    Models.get_models_by_ids(model_ids, db=db) if model_ids else []
                )
            }

            for model_data in data:
                # Here, you can add logic to validate model_data if needed
                model_id = model_data.get("id")

                if model_id and is_valid_model_id(model_id):
                    existing_model = existing_models.get(model_id)
                    if existing_model:
                        # Update existing model
                        model_data["meta"] = model_data.get("meta", {})
                        model_data["params"] = model_data.get("params", {})

                        updated_model = ModelForm(
                            **{**existing_model.model_dump(), **model_data}
                        )
                        Models.update_model_by_id(model_id, updated_model, db=db)
                    else:
                        # Insert new model
                        model_data["meta"] = model_data.get("meta", {})
                        model_data["params"] = model_data.get("params", {})
                        new_model = ModelForm(**model_data)
                        Models.insert_new_model(
                            user_id=user.id, form_data=new_model, db=db
                        )
            return True
        else:
            raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        log.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


############################
# SyncModels
############################


class SyncModelsForm(BaseModel):
    models: list[ModelModel] = []


@router.post("/sync", response_model=list[ModelModel])
async def sync_models(
    request: Request,
    form_data: SyncModelsForm,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    return Models.sync_models(user.id, form_data.models, db=db)


###########################
# GetModelById
###########################


class ModelIdForm(BaseModel):
    id: str


# Note: We're not using the typical url path param here, but instead using a query parameter to allow '/' in the id
@router.get("/model", response_model=Optional[ModelAccessResponse])
async def get_model_by_id(
    request: Request,
    id: str,
    raw: bool = False,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    model = Models.get_model_by_id(id, db=db)
    if model:
        if (
            (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
            or model.user_id == user.id
            or AccessGrants.has_access(
                user_id=user.id,
                resource_type="model",
                resource_id=model.id,
                permission="read",
                db=db,
            )
        ):
            write_access = (
                (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                or user.id == model.user_id
                or AccessGrants.has_access(
                    user_id=user.id,
                    resource_type="model",
                    resource_id=model.id,
                    permission="write",
                    db=db,
                )
            )
            if raw:
                return ModelAccessResponse(**model.model_dump(), write_access=write_access)

            return build_model_response_with_defaults(request, model, write_access)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )

    local_model = get_local_base_model_by_id(id)
    if local_model and user.role == "admin":
        timestamp = int(local_model.get("loaded_at") or time.time())
        default_params = getattr(request.app.state.config, "DEFAULT_MODEL_PARAMS", None) or {}
        default_metadata = getattr(request.app.state.config, "DEFAULT_MODEL_METADATA", None) or {}

        return ModelAccessResponse(
            id=id,
            user_id=user.id,
            base_model_id=None,
            name=local_model_display_name(local_model),
            params={} if raw else get_effective_model_params(None, default_params),
            meta={} if raw else get_effective_model_metadata({}, default_metadata, user_customized=False),
            access_grants=[],
            is_active=True,
            updated_at=timestamp,
            created_at=timestamp,
            write_access=True,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=ERROR_MESSAGES.NOT_FOUND,
    )

###########################
# GetModelById
###########################


@router.get("/model/profile/image")
def get_model_profile_image(id: str, user=Depends(get_verified_user)):
    model = Models.get_model_by_id(id)

    if model:
        meta = model.meta.model_dump() if model.meta else {}
        profile_image_url = (
            llamacpp.get_catalog_profile_image_url(meta)
            or meta.get("profile_image_url")
        )
        etag = (
            f'"{model.updated_at}:{profile_image_url or "default"}"'
            if model.updated_at
            else None
        )

        static_response = get_static_profile_image_response(profile_image_url, etag)
        if static_response:
            return static_response

        if profile_image_url:
            if profile_image_url.startswith("http"):
                return Response(
                    status_code=status.HTTP_302_FOUND,
                    headers={"Location": profile_image_url},
                )
            elif profile_image_url.startswith("data:image"):
                try:
                    header, base64_data = profile_image_url.split(",", 1)
                    image_data = base64.b64decode(base64_data)
                    image_buffer = io.BytesIO(image_data)
                    media_type = header.split(";")[0].lstrip("data:")

                    headers = {"Content-Disposition": "inline"}
                    if etag:
                        headers["ETag"] = etag

                    return StreamingResponse(
                        image_buffer,
                        media_type=media_type,
                        headers=headers,
                    )
                except Exception as e:
                    pass

        return FileResponse(f"{STATIC_DIR}/favicon.png")
    else:
        return FileResponse(f"{STATIC_DIR}/favicon.png")


############################
# ToggleModelById
############################


@router.post("/model/toggle", response_model=Optional[ModelResponse])
async def toggle_model_by_id(
    id: str, user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    model = Models.get_model_by_id(id, db=db)
    if model:
        if (
            user.role == "admin"
            or model.user_id == user.id
            or AccessGrants.has_access(
                user_id=user.id,
                resource_type="model",
                resource_id=model.id,
                permission="write",
                db=db,
            )
        ):
            model = Models.toggle_model_by_id(id, db=db)

            if model:
                return model
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error updating function"),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.UNAUTHORIZED,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdateModelById
############################


@router.post("/model/update", response_model=Optional[ModelModel])
async def update_model_by_id(
    request: Request,
    form_data: ModelForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    model = Models.get_model_by_id(form_data.id, db=db)
    if not model:
        local_model = get_local_base_model_by_id(form_data.id)
        if local_model and user.role == "admin":
            form_data = mark_model_form_user_customized(form_data)
            model = Models.insert_new_model(form_data, user.id, db=db)
            if model:
                request.app.state.BASE_MODELS = None
                return model

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        model.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="model",
            resource_id=model.id,
            permission="write",
            db=db,
        )
        and user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    form_data = mark_model_form_user_customized(form_data)
    form_data = lock_neve_catalog_profile_image(model, form_data)
    model = Models.update_model_by_id(form_data.id, ModelForm(**form_data.model_dump()), db=db)
    request.app.state.BASE_MODELS = None
    return model


############################
# UpdateModelAccessById
############################


class ModelAccessGrantsForm(BaseModel):
    id: str
    name: Optional[str] = None
    access_grants: list[dict]


@router.post("/model/access/update", response_model=Optional[ModelModel])
async def update_model_access_by_id(
    request: Request,
    form_data: ModelAccessGrantsForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    model = Models.get_model_by_id(form_data.id, db=db)

    # Non-preset models (e.g. direct Ollama/OpenAI models) may not have a DB
    # entry yet. Create a minimal one so access grants can be stored.
    if not model:
        if user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )
        model = Models.insert_new_model(
            ModelForm(
                id=form_data.id,
                name=form_data.name or form_data.id,
                meta=ModelMeta(),
                params=ModelParams(),
            ),
            user.id,
            db=db,
        )
        if not model:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ERROR_MESSAGES.DEFAULT("Error creating model entry"),
            )

    if (
        model.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="model",
            resource_id=model.id,
            permission="write",
            db=db,
        )
        and user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    form_data.access_grants = filter_allowed_access_grants(
        request.app.state.config.USER_PERMISSIONS,
        user.id,
        user.role,
        form_data.access_grants,
        "sharing.public_models",
    )

    AccessGrants.set_access_grants(
        "model", form_data.id, form_data.access_grants, db=db
    )

    return Models.get_model_by_id(form_data.id, db=db)


############################
# DeleteModelById
############################


@router.post("/model/delete", response_model=bool)
async def delete_model_by_id(
    form_data: ModelIdForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    model = Models.get_model_by_id(form_data.id, db=db)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        user.role != "admin"
        and model.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="model",
            resource_id=model.id,
            permission="write",
            db=db,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    result = Models.delete_model_by_id(form_data.id, db=db)
    return result


@router.delete("/delete/all", response_model=bool)
async def delete_all_models(
    user=Depends(get_admin_user), db: Session = Depends(get_session)
):
    result = Models.delete_all_models(db=db)
    return result
