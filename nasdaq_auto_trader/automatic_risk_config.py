from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .ai_quant_lab.config import (
    AIQuantConfig,
    BOOL_FIELDS,
    FLOAT_FIELDS,
    INT_FIELDS,
    STR_FIELDS,
    STR_SEQUENCE_FIELDS,
    load_ai_quant_config,
    validate_ai_quant_config,
)
from .ai_quant_lab.strategy_schema_safety import (
    NonFiniteJsonNumberError,
    parse_finite_json_float,
    reject_non_finite_json,
)


@dataclass(frozen=True, slots=True)
class AutomaticRiskConfigBlock:
    reason: str


def load_automatic_risk_config(
    path: Path | None,
) -> AIQuantConfig | AutomaticRiskConfigBlock:
    if path is None or not path.exists():
        return AIQuantConfig()
    try:
        with path.open("r", encoding="utf-8") as source:
            payload = json.load(
                source,
                parse_constant=reject_non_finite_json,
                parse_float=parse_finite_json_float,
            )
    except (json.JSONDecodeError, NonFiniteJsonNumberError, OSError):
        return AutomaticRiskConfigBlock("ai_quant_config_invalid")
    if not isinstance(payload, dict) or any(
        not _field_type_valid(key, value) for key, value in payload.items()
    ):
        return AutomaticRiskConfigBlock("ai_quant_config_invalid")
    config = load_ai_quant_config(path)
    if not validate_ai_quant_config(config).valid:
        return AutomaticRiskConfigBlock("ai_quant_config_invalid")
    return config


def learned_risk_config_digest(path: Path | None) -> str:
    loaded = load_automatic_risk_config(path)
    if isinstance(loaded, AutomaticRiskConfigBlock):
        return "invalid"
    payload = json.dumps(
        loaded.to_json_object(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _field_type_valid(key: str, value) -> bool:
    if key in BOOL_FIELDS:
        return isinstance(value, bool)
    if key in INT_FIELDS:
        return isinstance(value, int) and not isinstance(value, bool)
    if key in FLOAT_FIELDS:
        if not isinstance(value, int | float) or isinstance(value, bool):
            return False
        try:
            return math.isfinite(float(value))
        except OverflowError:
            return False
    if key in STR_FIELDS:
        return isinstance(value, str)
    if key in STR_SEQUENCE_FIELDS:
        return isinstance(value, list) and all(
            isinstance(item, str) and bool(item.strip()) for item in value
        )
    return True
