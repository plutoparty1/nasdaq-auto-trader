from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Final

from .types import JsonObject, JsonValue

ALLOWED_TOP_LEVEL_FIELDS: Final = {
    "strategy_id",
    "version",
    "strategy_family",
    "description",
    "research_basis",
    "universe",
    "signals",
    "entry_rule",
    "exit_rule",
    "position_sizing",
    "risk_controls",
    "metadata",
}

DANGEROUS_FIELD_NAMES: Final = {
    "broker",
    "broker_order",
    "command",
    "eval",
    "exec",
    "order",
    "order_api",
    "order_qty",
    "orders",
    "python_code",
    "qty",
    "quantity",
    "raw_order",
    "shell",
    "submit_order",
}

ALLOWED_OBJECT_FIELDS: Final = {
    "research_basis": {"provider", "research_ids", "source_ids", "summary"},
    "universe": {"symbols", "selection_method", "filters"},
    "universe.filters": {
        "min_price",
        "max_price",
        "min_dollar_volume",
        "max_spread_pct",
        "exclude_halted",
        "stale_data_seconds",
    },
    "signals[]": {
        "type",
        "weight",
        "lookback_days",
        "zscore_window",
        "rsi_period",
        "atr_window",
        "factor_names",
    },
    "entry_rule": {"type", "threshold", "top_n"},
    "exit_rule": {
        "stop_loss_mode",
        "stop_loss_atr_multiple",
        "take_profit_mode",
        "take_profit_atr_multiple",
        "trailing_stop",
        "max_holding_days",
    },
    "position_sizing": {
        "method",
        "risk_per_trade_pct",
        "confidence_adjusted",
        "max_single_position_pct",
    },
    "risk_controls": {
        "use_kill_switch",
        "block_if_data_stale",
        "block_if_spread_abnormal",
        "block_if_daily_loss_limit",
        "block_before_market_close",
    },
    "metadata": {"created_by", "created_at"},
}

SIGNAL_NUMERIC_PARAMETERS: Final = {
    "lookback_days",
    "zscore_window",
    "rsi_period",
    "atr_window",
}
STRING_FIELDS: Final = {
    "strategy_id",
    "version",
    "strategy_family",
    "description",
    "research_basis.provider",
    "research_basis.summary",
    "universe.selection_method",
    "signals[].type",
    "entry_rule.type",
    "exit_rule.stop_loss_mode",
    "exit_rule.take_profit_mode",
    "position_sizing.method",
    "metadata.created_by",
    "metadata.created_at",
}
STRING_LIST_FIELDS: Final = {
    "research_basis.research_ids",
    "research_basis.source_ids",
    "universe.symbols",
    "signals[].factor_names",
}


@dataclass(frozen=True, slots=True)
class NonFiniteJsonNumberError(ValueError):
    token: str

    def __str__(self) -> str:
        return f"non-finite JSON number: {self.token}"


def reject_non_finite_json(token: str) -> None:
    raise NonFiniteJsonNumberError(token)


def parse_finite_json_float(token: str) -> float:
    value = float(token)
    if not isfinite(value):
        raise NonFiniteJsonNumberError(token)
    return value


def schema_rejection_reasons(payload: Mapping[str, JsonValue]) -> list[str]:
    reasons = [f"unknown_field:{key}" for key in payload if key not in ALLOWED_TOP_LEVEL_FIELDS]
    reasons.extend(_nested_unknown_reasons(payload))
    reasons.extend(_type_shape_reasons(payload))
    reasons.extend(f"field_not_allowed:{path}" for path in _dangerous_paths(payload, ""))
    return reasons


def bool_field(
    data: Mapping[str, JsonValue],
    key: str,
    reasons: list[str],
    default: bool,
) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    reasons.append(f"{key}_must_be_bool")
    return default


def is_json_number(value: JsonValue | None) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and isfinite(float(value))


def is_json_int(value: JsonValue | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def signal_parameters(
    data: Mapping[str, JsonValue],
    reasons: list[str],
) -> JsonObject:
    parameters: JsonObject = {}
    for key, value in data.items():
        if key in ("type", "weight"):
            continue
        if key in SIGNAL_NUMERIC_PARAMETERS:
            if is_json_number(value):
                parameters[key] = value
            else:
                reasons.append(f"signal_parameter_{key}_must_be_number")
        elif key == "factor_names":
            if _is_string_list(value):
                parameters[key] = value
            else:
                reasons.append("signal_parameter_factor_names_must_be_string_list")
        else:
            parameters[key] = value
    return parameters


def _is_string_list(value: JsonValue | None) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _nested_unknown_reasons(payload: Mapping[str, JsonValue]) -> list[str]:
    reasons: list[str] = []
    for key, value in payload.items():
        if key in ALLOWED_OBJECT_FIELDS and isinstance(value, dict):
            reasons.extend(_unknown_object_reasons(value, key))
            if key == "universe" and isinstance(value.get("filters"), dict):
                reasons.extend(_unknown_object_reasons(value["filters"], "universe.filters"))
        if key == "signals" and isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    reasons.extend(_unknown_object_reasons(item, f"signals[{index}]", "signals[]"))
    return reasons


def _unknown_object_reasons(
    data: Mapping[str, JsonValue],
    path: str,
    shape: str | None = None,
) -> list[str]:
    allowed = ALLOWED_OBJECT_FIELDS[shape or path]
    return [f"unknown_field:{path}.{key}" for key in data if key not in allowed]


def _type_shape_reasons(payload: Mapping[str, JsonValue]) -> list[str]:
    reasons: list[str] = []
    for key, value in payload.items():
        reasons.extend(_path_type_reasons(value, key))
    return reasons


def _path_type_reasons(value: JsonValue | None, path: str) -> list[str]:
    normalized = _normalize_path(path)
    if normalized in STRING_FIELDS:
        return [] if isinstance(value, str) else [f"{path}_must_be_string"]
    if normalized in STRING_LIST_FIELDS:
        return [] if _is_string_list(value) else [f"{path}_must_be_string_list"]
    if normalized in ALLOWED_OBJECT_FIELDS:
        if not isinstance(value, dict):
            return [f"{path}_must_be_object"]
        reasons: list[str] = []
        for key, item in value.items():
            reasons.extend(_path_type_reasons(item, f"{path}.{key}"))
        return reasons
    if normalized == "signals":
        if not isinstance(value, list):
            return ["signals_must_be_list"]
        return _signal_item_type_reasons(value)
    if isinstance(value, dict | list):
        return [f"{path}_must_be_scalar"]
    return []


def _signal_item_type_reasons(items: list[JsonValue]) -> list[str]:
    reasons: list[str] = []
    for index, item in enumerate(items):
        if isinstance(item, dict):
            reasons.extend(_path_type_reasons(item, f"signals[{index}]"))
        else:
            reasons.append(f"signals[{index}]_must_be_object")
    return reasons


def _normalize_path(path: str) -> str:
    if not path.startswith("signals["):
        return path
    close = path.find("]")
    if close == -1:
        return path
    return f"signals[]{path[close + 1:]}"


def _dangerous_paths(value: JsonValue | None, prefix: str) -> tuple[str, ...]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in DANGEROUS_FIELD_NAMES:
                paths.append(path)
            paths.extend(_dangerous_paths(item, path))
        return tuple(paths)
    if isinstance(value, list):
        paths: list[str] = []
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            paths.extend(_dangerous_paths(item, path))
        return tuple(paths)
    return ()
