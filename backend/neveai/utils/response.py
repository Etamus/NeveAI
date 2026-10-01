def normalize_usage(usage: dict) -> dict:
    """Normalize local llama.cpp usage statistics."""
    if not usage:
        return {}

    def as_float(value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(",", "."))
            except ValueError:
                return None
        return None

    input_tokens = usage.get("input_tokens") or usage.get("prompt_n") or 0
    output_tokens = usage.get("output_tokens") or usage.get("predicted_n") or 0
    total_tokens = usage.get("total_tokens") or input_tokens + output_tokens

    tokens_per_second = None
    for key in (
        "tokens_per_second",
        "output_tokens_per_second",
        "completion_tokens_per_second",
        "response_tokens_per_second",
        "response_token/s",
        "tokens/s",
        "predicted_per_second",
    ):
        tokens_per_second = as_float(usage.get(key))
        if tokens_per_second is not None:
            break

    if tokens_per_second is None:
        predicted_ms = as_float(usage.get("predicted_ms"))
        predicted_n = as_float(usage.get("predicted_n")) or float(output_tokens)
        if predicted_ms and predicted_ms > 0:
            tokens_per_second = predicted_n / (predicted_ms / 1000)

    result = dict(usage)
    result["input_tokens"] = int(input_tokens)
    result["output_tokens"] = int(output_tokens)
    result["total_tokens"] = int(total_tokens)
    if tokens_per_second is not None:
        result["tokens_per_second"] = round(tokens_per_second, 2)
    return result
