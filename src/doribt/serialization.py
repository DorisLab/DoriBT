"""Canonical finite JSON shared by run metadata and research extensions."""

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any


def _encode(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported serialized value: {type(value).__name__}")


def encode(value: object) -> str:
    return json.dumps(value, default=_encode, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def _json_parameter(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("parameter object keys must be strings")
            _json_parameter(item)
    elif isinstance(value, list):
        for item in value:
            _json_parameter(item)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("parameters must contain only JSON objects, lists and scalars")


def parameters_copy(parameters: Mapping[str, object] | None) -> dict[str, Any]:
    values = dict(parameters or {})
    _json_parameter(values)
    copied: dict[str, Any] = json.loads(encode(values))
    return copied
