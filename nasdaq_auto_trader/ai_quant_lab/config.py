from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from typing import Final, TypeAlias

from .types import JsonObject, JsonValue
from .strategy_schema_safety import (
    NonFiniteJsonNumberError,
    parse_finite_json_float,
    reject_non_finite_json,
)

INSANE_SEARCH_PROVIDER: Final = "insane_search"
BOOL_FIELDS: Final = {
    "ai_quant_lab_enabled",
    "self_improvement_enabled",
    "allow_only_insane_search_for_research",
    "disable_research_if_insane_search_unavailable",
    "require_research_sources_for_strategy_generation",
    "live_trading",
    "dry_run",
    "paper_trading_enabled",
    "shadow_live_enabled",
    "controlled_live_enabled",
    "allow_ai_strategy_generation",
    "allow_ai_direct_order",
    "allow_dynamic_code_execution",
    "universe_auto_select_enabled",
    "promotion_requires_manual_approval",
    "champion_requires_manual_approval",
    "allowed_for_live_default",
    "spread_filter_enabled",
    "kill_switch_enabled",
    "fail_closed",
}
INT_FIELDS: Final = {
    "max_strategy_candidates_per_run",
    "max_parallel_backtests",
    "insane_search_timeout_seconds",
    "min_oos_months",
    "min_paper_trading_days",
    "min_shadow_live_days",
    "max_orders_per_day",
    "stale_data_seconds",
}
FLOAT_FIELDS: Final = {
    "max_single_position_pct",
    "max_total_exposure_pct",
    "max_daily_loss_pct",
    "max_strategy_drawdown_pct",
    "max_order_notional",
    "commission_bps",
    "slippage_bps",
}
STR_FIELDS: Final = {"research_provider", "universe_source"}
STR_SEQUENCE_FIELDS: Final = {"insane_search_command"}
ConfigFieldValue: TypeAlias = JsonValue | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AIQuantConfig:
    ai_quant_lab_enabled: bool = False
    self_improvement_enabled: bool = False
    research_provider: str = INSANE_SEARCH_PROVIDER
    insane_search_command: tuple[str, ...] = ()
    insane_search_timeout_seconds: int = 60
    allow_only_insane_search_for_research: bool = True
    disable_research_if_insane_search_unavailable: bool = True
    require_research_sources_for_strategy_generation: bool = True
    live_trading: bool = False
    dry_run: bool = True
    paper_trading_enabled: bool = True
    shadow_live_enabled: bool = False
    controlled_live_enabled: bool = False
    allow_ai_strategy_generation: bool = True
    allow_ai_direct_order: bool = False
    allow_dynamic_code_execution: bool = False
    universe_source: str = "nasdaq_all"
    universe_auto_select_enabled: bool = True
    max_strategy_candidates_per_run: int = 10
    max_parallel_backtests: int = 4
    min_oos_months: int = 6
    min_paper_trading_days: int = 20
    min_shadow_live_days: int = 10
    promotion_requires_manual_approval: bool = True
    champion_requires_manual_approval: bool = True
    allowed_for_live_default: bool = False
    max_single_position_pct: float = 0.05
    max_total_exposure_pct: float = 0.30
    max_daily_loss_pct: float = 0.02
    max_strategy_drawdown_pct: float = 0.10
    max_order_notional: float = 1000.0
    max_orders_per_day: int = 5
    commission_bps: float = 1.0
    slippage_bps: float = 5.0
    spread_filter_enabled: bool = True
    stale_data_seconds: int = 60
    kill_switch_enabled: bool = True
    fail_closed: bool = True

    def to_json_object(self) -> JsonObject:
        payload = asdict(self)
        payload["insane_search_command"] = list(self.insane_search_command)
        return payload


@dataclass(frozen=True, slots=True)
class ConfigValidationResult:
    valid: bool
    reasons: tuple[str, ...]


def load_ai_quant_config(path: str | Path | None = None) -> AIQuantConfig:
    if path is None:
        return AIQuantConfig()
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw = json.load(
                file,
                parse_constant=reject_non_finite_json,
                parse_float=parse_finite_json_float,
            )
    except (json.JSONDecodeError, NonFiniteJsonNumberError, OSError):
        return AIQuantConfig()
    if not isinstance(raw, dict):
        return AIQuantConfig()
    if _has_malformed_known_field(raw):
        return AIQuantConfig()
    values = _typed_config_values(raw)
    return AIQuantConfig(**values)


def validate_ai_quant_config(config: AIQuantConfig) -> ConfigValidationResult:
    reasons = _type_validation_reasons(config)
    if reasons:
        return ConfigValidationResult(False, tuple(reasons))
    if config.research_provider != INSANE_SEARCH_PROVIDER:
        reasons.append("research_provider_must_be_insane_search")
    if not _is_string_tuple(config.insane_search_command):
        reasons.append("insane_search_command_must_be_string_list")
    if (
        not isinstance(config.insane_search_timeout_seconds, int)
        or isinstance(config.insane_search_timeout_seconds, bool)
    ):
        reasons.append("insane_search_timeout_seconds_must_be_int")
    elif config.insane_search_timeout_seconds < 1:
        reasons.append("insane_search_timeout_seconds_must_be_positive")
    if not config.allow_only_insane_search_for_research:
        reasons.append("allow_only_insane_search_for_research_must_be_true")
    if not config.disable_research_if_insane_search_unavailable:
        reasons.append("disable_research_if_insane_search_unavailable_must_be_true")
    if config.allow_ai_direct_order:
        reasons.append("allow_ai_direct_order_must_be_false")
    if config.allow_dynamic_code_execution:
        reasons.append("allow_dynamic_code_execution_must_be_false")
    if not 0 < config.max_single_position_pct <= 1:
        reasons.append("max_single_position_pct_out_of_range")
    if not 0 < config.max_total_exposure_pct <= 1:
        reasons.append("max_total_exposure_pct_out_of_range")
    if not 0 < config.max_daily_loss_pct <= 1:
        reasons.append("max_daily_loss_pct_out_of_range")
    if config.max_order_notional <= 0:
        reasons.append("max_order_notional_must_be_positive")
    if config.max_orders_per_day < 1:
        reasons.append("max_orders_per_day_must_be_positive")
    return ConfigValidationResult(valid=not reasons, reasons=tuple(reasons))


def live_order_block_reason(config: AIQuantConfig) -> str | None:
    if not validate_ai_quant_config(config).valid:
        return "ai_quant_config_invalid"
    if not config.live_trading:
        return "live_trading_disabled"
    if config.dry_run:
        return "dry_run_enabled"
    if not config.controlled_live_enabled:
        return "controlled_live_disabled"
    return None


def _typed_config_values(raw: Mapping[str, JsonValue]) -> dict[str, ConfigFieldValue]:
    values: dict[str, ConfigFieldValue] = {}
    for key, value in raw.items():
        if key in BOOL_FIELDS and isinstance(value, bool):
            values[key] = value
        elif key in INT_FIELDS and isinstance(value, int) and not isinstance(value, bool):
            values[key] = value
        elif key in FLOAT_FIELDS and _is_number(value):
            values[key] = float(value)
        elif key in STR_FIELDS and isinstance(value, str):
            values[key] = value
        elif key in STR_SEQUENCE_FIELDS and _is_json_string_sequence(value):
            values[key] = tuple(item.strip() for item in value)
    return values


def _has_malformed_known_field(raw: Mapping[str, JsonValue]) -> bool:
    return any(_known_field_malformed(key, value) for key, value in raw.items())


def _known_field_malformed(key: str, value: JsonValue) -> bool:
    if key in BOOL_FIELDS:
        return not isinstance(value, bool)
    if key in INT_FIELDS:
        return not isinstance(value, int) or isinstance(value, bool)
    if key in FLOAT_FIELDS:
        return not _is_number(value)
    if key in STR_FIELDS:
        return not isinstance(value, str)
    if key in STR_SEQUENCE_FIELDS:
        return not _is_json_string_sequence(value)
    return False


def _type_validation_reasons(config: AIQuantConfig) -> list[str]:
    reasons: list[str] = []
    for key in (
        "live_trading",
        "dry_run",
        "controlled_live_enabled",
        "allow_ai_direct_order",
        "allow_dynamic_code_execution",
        "allow_only_insane_search_for_research",
        "disable_research_if_insane_search_unavailable",
    ):
        if not isinstance(getattr(config, key), bool):
            reasons.append(f"{key}_must_be_bool")
    if not isinstance(config.research_provider, str):
        reasons.append("research_provider_must_be_string")
    if not _is_string_tuple(config.insane_search_command):
        reasons.append("insane_search_command_must_be_string_tuple")
    for key in (
        "max_single_position_pct",
        "max_total_exposure_pct",
        "max_daily_loss_pct",
        "max_order_notional",
    ):
        if not _is_number(getattr(config, key)):
            reasons.append(f"{key}_must_be_number")
    if not isinstance(config.max_orders_per_day, int) or isinstance(config.max_orders_per_day, bool):
        reasons.append("max_orders_per_day_must_be_int")
    return reasons


def _is_json_string_sequence(value: JsonValue | None) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def _is_string_tuple(value: JsonValue | tuple[str, ...]) -> bool:
    return isinstance(value, tuple) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def _is_number(value: JsonValue | None) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and isfinite(float(value))
