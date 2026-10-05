import json
from typing import Callable, Optional

from neveai.utils.misc import (
    add_or_update_system_message,
    deep_update,
    replace_system_message_content,
)
from neveai.utils.task import prompt_template, prompt_variables_template


def apply_system_prompt_to_body(
    system: Optional[str],
    form_data: dict,
    metadata: Optional[dict] = None,
    user=None,
    replace: bool = False,
) -> dict:
    if not system:
        return form_data

    if metadata and (variables := metadata.get("variables", {})):
        system = prompt_variables_template(system, variables)

    system = prompt_template(system, user)
    if replace:
        form_data["messages"] = replace_system_message_content(
            system, form_data.get("messages", [])
        )
    else:
        form_data["messages"] = add_or_update_system_message(
            system, form_data.get("messages", [])
        )
    return form_data


def apply_model_params_to_body(
    params: dict, form_data: dict, mappings: dict[str, Callable]
) -> dict:
    if not params:
        return form_data

    for key, value in params.items():
        if value is None:
            continue
        if key in mappings and isinstance(mappings[key], Callable):
            form_data[key] = mappings[key](value)
        else:
            form_data[key] = value
    return form_data


def remove_neveai_params(params: dict) -> dict:
    for key in (
        "stream_response",
        "stream_delta_chunk_size",
        "function_calling",
        "reasoning_tags",
        "reasoning_extended",
        "reasoning_unlimited",
        "reasoning_mode",
        "system",
    ):
        params.pop(key, None)
    return params


def apply_model_params_to_body_openai(params: dict, form_data: dict) -> dict:
    params = remove_neveai_params(params)
    custom_params = params.pop("custom_params", {})
    for key, value in custom_params.items():
        if isinstance(value, str):
            try:
                custom_params[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    if custom_params:
        params = deep_update(params, custom_params)

    mappings = {
        "temperature": float,
        "top_p": float,
        "min_p": float,
        "max_tokens": int,
        "frequency_penalty": float,
        "presence_penalty": float,
        "reasoning_effort": str,
        "seed": lambda value: value,
        "stop": lambda values: [
            bytes(value, "utf-8").decode("unicode_escape") for value in values
        ],
        "logit_bias": lambda value: value,
        "response_format": dict,
    }
    return apply_model_params_to_body(params, form_data, mappings)
