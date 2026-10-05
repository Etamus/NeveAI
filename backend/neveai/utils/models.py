import logging
import sys

from fastapi import Request

from neveai.socket.utils import RedisDict
from neveai.routers import llamacpp
from neveai.models.models import Models
from neveai.models.access_grants import AccessGrants
from neveai.models.groups import Groups
from neveai.utils.model_defaults import apply_default_model_metadata, model_has_user_edits
from neveai.config import BYPASS_ADMIN_ACCESS_CONTROL
from neveai.env import BYPASS_MODEL_ACCESS_CONTROL, GLOBAL_LOG_LEVEL
from neveai.models.users import UserModel

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)


async def fetch_llamacpp_models(request: Request = None, user: UserModel = None):
    try:
        raw = await llamacpp.get_all_models(request, user)
        return raw.get("models", [])
    except Exception as e:
        log.warning(f"Error fetching local GGUF models: {e}")
        return []


async def get_all_base_models(request: Request, user: UserModel = None):
    return await fetch_llamacpp_models(request, user)


async def get_all_models(request, refresh: bool = False, user: UserModel = None):
    if (
        request.app.state.MODELS
        and request.app.state.BASE_MODELS
        and request.app.state.config.ENABLE_BASE_MODELS_CACHE
        and not refresh
    ):
        base_models = request.app.state.BASE_MODELS
    else:
        base_models = await get_all_base_models(request, user=user)
        request.app.state.BASE_MODELS = base_models

    models = [model.copy() for model in base_models]
    base_model_lookup = {model["id"]: model for model in models}
    existing_ids = set(base_model_lookup)

    for custom_model in Models.get_all_models():
        if custom_model.base_model_id is None:
            model = base_model_lookup.get(custom_model.id)
            if model and custom_model.is_active:
                model["name"] = custom_model.name
                model["info"] = custom_model.model_dump()
                if model_has_user_edits(custom_model):
                    model["info"]["_skip_global_model_defaults"] = True
                model["info"].pop("params", None)
            elif model and not custom_model.is_active:
                models.remove(model)
            continue

        if not custom_model.is_active or custom_model.id in existing_ids:
            continue

        base_model = base_model_lookup.get(custom_model.base_model_id)
        if base_model is None:
            continue

        info = custom_model.model_dump()
        if model_has_user_edits(custom_model):
            info["_skip_global_model_defaults"] = True
        info.pop("params", None)
        models.append(
            {
                "id": custom_model.id,
                "name": custom_model.name,
                "object": "model",
                "created": custom_model.created_at,
                "owned_by": base_model.get("owned_by", "llamacpp"),
                "connection_type": base_model.get("connection_type"),
                "preset": True,
                "info": info,
            }
        )

    default_metadata = getattr(request.app.state.config, "DEFAULT_MODEL_METADATA", None) or {}
    if default_metadata:
        for model in models:
            apply_default_model_metadata(model, default_metadata)

    models_dict = {model["id"]: model for model in models}
    if isinstance(request.app.state.MODELS, RedisDict):
        request.app.state.MODELS.set(models_dict)
    else:
        request.app.state.MODELS = models_dict
    return models


def check_model_access(user, model, db=None):
    model_info = Models.get_model_by_id(model.get("id"), db=db)
    if not model_info:
        raise Exception("Model not found")
    elif not (
        user.id == model_info.user_id
        or AccessGrants.has_access(
            user_id=user.id,
            resource_type="model",
            resource_id=model_info.id,
            permission="read",
            db=db,
        )
    ):
        raise Exception("Model not found")


def get_filtered_models(models, user, db=None):
    # Filter out models that the user does not have access to
    if (
        user.role == "user"
        or (user.role == "admin" and not BYPASS_ADMIN_ACCESS_CONTROL)
    ) and not BYPASS_MODEL_ACCESS_CONTROL:
        model_infos = {}
        for model in models:
            info = model.get("info")
            if info:
                model_infos[model["id"]] = info

        user_group_ids = {
            group.id for group in Groups.get_groups_by_member_id(user.id, db=db)
        }

        # Batch-fetch accessible resource IDs in a single query instead of N has_access calls
        accessible_model_ids = AccessGrants.get_accessible_resource_ids(
            user_id=user.id,
            resource_type="model",
            resource_ids=list(model_infos.keys()),
            permission="read",
            user_group_ids=user_group_ids,
            db=db,
        )

        filtered_models = []
        for model in models:

            model_info = model_infos.get(model["id"])
            if model_info:
                if (
                    (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or user.id == model_info.get("user_id")
                    or model["id"] in accessible_model_ids
                ):
                    filtered_models.append(model)

        return filtered_models
    else:
        return models
