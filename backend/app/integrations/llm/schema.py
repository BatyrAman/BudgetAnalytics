"""Turn a Pydantic model into a provider-friendly STRICT JSON Schema.

Strict structured-output modes (e.g. OpenAI ``json_schema`` with
``strict: true``) require every object to list all properties as required
and to set ``additionalProperties: false``, and they reject some validation
keywords. Those keywords are stripped here; the full constraints are still
enforced afterwards by Pydantic validation of the model's answer.
"""

from typing import Any

from pydantic import BaseModel

# Validation keywords removed for the provider (still enforced by Pydantic).
_UNSUPPORTED = {
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "default",
    "examples",
}


# Keys whose value maps NAMES to schemas: the names themselves are data
# (a property may well be called "format" or "default") and must be kept.
_NAME_MAPS = {"properties", "$defs", "definitions"}


def _strict(node: Any) -> Any:
    if isinstance(node, dict):
        cleaned: dict[str, Any] = {}
        for key, value in node.items():
            if key in _NAME_MAPS and isinstance(value, dict):
                cleaned[key] = {name: _strict(sub) for name, sub in value.items()}
            elif key not in _UNSUPPORTED:
                cleaned[key] = _strict(value)
        if cleaned.get("type") == "object" and "properties" in cleaned:
            cleaned["required"] = list(cleaned["properties"].keys())
            cleaned["additionalProperties"] = False
        return cleaned
    if isinstance(node, list):
        return [_strict(item) for item in node]
    return node


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    return _strict(model.model_json_schema())
