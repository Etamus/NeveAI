import copy

from neveai.models.models import ModelForm


IGNORED_PARAM_KEYS = {"cache_type"}
MODEL_DEFAULT_BLOCKING_META_KEYS = {"capabilities", "defaultFeatureIds", "builtinTools"}


def _model_dump(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return dict(value)
    return {}


def _get_model_value(model_info, key):
    if isinstance(model_info, dict):
        return model_info.get(key)
    return getattr(model_info, key, None)


def _has_meaningful_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, dict):
        return any(_has_meaningful_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_meaningful_value(item) for item in value)
    return True


def model_has_defined_params(model_info) -> bool:
    model_data = _model_dump(model_info)
    params = _model_dump(_get_model_value(model_info, "params") or model_data.get("params"))

    return any(
        key not in IGNORED_PARAM_KEYS and _has_meaningful_value(value)
        for key, value in params.items()
    )


def model_has_defined_defaults_metadata(model_info) -> bool:
    model_data = _model_dump(model_info)
    meta = _model_dump(_get_model_value(model_info, "meta") or model_data.get("meta"))

    return any(
        _has_meaningful_value(meta.get(key)) for key in MODEL_DEFAULT_BLOCKING_META_KEYS
    )


def model_has_user_edits(model_info) -> bool:
    if not model_info:
        return False

    model_data = _model_dump(model_info)
    meta = _model_dump(_get_model_value(model_info, "meta") or model_data.get("meta"))

    if meta.get("user_customized") is True or meta.get("managed_by") == "user":
        return True

    if model_has_defined_params(model_info) or model_has_defined_defaults_metadata(model_info):
        return True

    return False


def mark_model_form_user_customized(form_data: ModelForm) -> ModelForm:
    model_data = form_data.model_dump()
    meta = _model_dump(model_data.get("meta"))
    meta["user_customized"] = True

    if meta.get("managed_by") == "neve_download":
        meta["managed_by"] = "user"

    model_data["meta"] = meta
    return ModelForm(**model_data)


def get_effective_model_params(model_info=None, default_params=None) -> dict:
    params = _model_dump(_get_model_value(model_info, "params"))
    params = {
        key: value
        for key, value in params.items()
        if key not in IGNORED_PARAM_KEYS and _has_meaningful_value(value)
    }
    defaults = {
        key: copy.deepcopy(value)
        for key, value in (default_params or {}).items()
        if key not in IGNORED_PARAM_KEYS and _has_meaningful_value(value)
    }

    if model_has_user_edits(model_info):
        return params

    return {**params, **defaults}


def get_effective_model_metadata(meta=None, default_metadata=None, user_customized=False) -> dict:
    metadata = copy.deepcopy(_model_dump(meta))

    if user_customized:
        return metadata

    for key, value in (default_metadata or {}).items():
        if key == "capabilities":
            default_capabilities = copy.deepcopy(value or {})
            existing_capabilities = metadata.get("capabilities") or {}
            metadata["capabilities"] = {**existing_capabilities, **default_capabilities}
        else:
            metadata[key] = copy.deepcopy(value)

    return metadata


def apply_default_model_metadata(model: dict, default_metadata=None) -> dict:
    if not default_metadata:
        return model

    info = model.setdefault("info", {})
    if info.pop("_skip_global_model_defaults", False):
        return model

    meta = info.setdefault("meta", {})
    user_customized = model_has_user_edits(info)
    info["meta"] = get_effective_model_metadata(
        meta, default_metadata, user_customized=user_customized
    )
    return model
