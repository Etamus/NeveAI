import random
import logging
import sys

from fastapi import Request
from neveai.models.users import UserModel
from neveai.models.models import Models
from neveai.utils.models import check_model_access
from neveai.env import GLOBAL_LOG_LEVEL, BYPASS_MODEL_ACCESS_CONTROL


logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)


async def generate_embeddings(
    request: Request,
    form_data: dict,
    user: UserModel,
    bypass_filter: bool = False,
):
    """
    Dispatch and handle embeddings generation based on the model type.

    Args:
        request (Request): The FastAPI request context.
        form_data (dict): The input data sent to the endpoint.
        user (UserModel): The authenticated user.
        bypass_filter (bool): If True, disables access filtering (default False).

    Returns:
        dict: The embeddings response, following OpenAI API compatibility.
    """
    if BYPASS_MODEL_ACCESS_CONTROL:
        bypass_filter = True

    # Attach extra metadata from request.state if present
    if hasattr(request.state, "metadata"):
        if "metadata" not in form_data:
            form_data["metadata"] = request.state.metadata
        else:
            form_data["metadata"] = {
                **form_data["metadata"],
                **request.state.metadata,
            }

    # If "direct" flag present, use only that model
    if getattr(request.state, "direct", False) and hasattr(request.state, "model"):
        models = {
            request.state.model["id"]: request.state.model,
        }
    else:
        models = request.app.state.MODELS

    model_id = form_data.get("model")
    if model_id not in models:
        raise Exception("Model not found")
    model = models[model_id]

    # Access filtering
    if not getattr(request.state, "direct", False):
        if not bypass_filter and user.role == "user":
            check_model_access(user, model)

    raise Exception("Unsupported external embedding backend")
