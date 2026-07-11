from __future__ import annotations

from typing import Any

JsonObject = dict[str, Any]


class BrokerCredentialError(ValueError):
    pass


class BrokerOrderError(ValueError):
    pass


class BrokerRequestError(RuntimeError):
    pass


def _first_float(payload: JsonObject, *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            continue
    return default


def _first_output_dict(payload: JsonObject, key: str) -> JsonObject:
    output = payload.get(key) or {}
    if isinstance(output, list):
        return output[0] if output and isinstance(output[0], dict) else {}
    return output if isinstance(output, dict) else {}


def _compact_date(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("-", "")[:8]


def _format_price(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"
