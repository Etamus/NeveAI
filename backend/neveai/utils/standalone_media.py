"""Request-only identities for pipelines that do not use a chat model."""
from neveai.utils.access_control import has_permission

FEATURES = {
    "stable_diffusion": "ENABLE_STABLE_DIFFUSION",
    "video_generation": "ENABLE_VIDEO_GENERATION",
    "model3d_generation": "ENABLE_STABLE_DIFFUSION",
}


def media_request(model_id, features, config, user):
    if not isinstance(model_id, str) or not model_id.startswith("neve-media/"):
        return None
    key = model_id.removeprefix("neve-media/")
    if key not in FEATURES or [k for k in FEATURES if features.get(k) is True] != [key]:
        raise ValueError("Model not selected")
    if not getattr(config, FEATURES[key]) or (user.role != "admin" and (
        key == "model3d_generation" or not has_permission(user.id, "features." + key, config.USER_PERMISSIONS)
    )):
        raise ValueError("Media integration not available")
    return key
