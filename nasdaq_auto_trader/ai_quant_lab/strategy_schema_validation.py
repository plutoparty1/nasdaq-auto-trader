from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Mapping

from .strategy_schema import (
    EntryRule,
    ExitRule,
    PositionSizingSpec,
    ResearchBasis,
    RiskControls,
    SignalSpec,
    SignalType,
    StrategyFamily,
    StrategySpec,
    StrategySpecValidation,
)
from .strategy_schema_safety import (
    NonFiniteJsonNumberError,
    bool_field,
    is_json_int,
    is_json_number,
    parse_finite_json_float,
    reject_non_finite_json,
    schema_rejection_reasons,
    signal_parameters,
)
from .types import JsonValue


def parse_strategy_spec_json(raw_text: str) -> StrategySpecValidation:
    text = raw_text.strip()
    if not text.startswith("{") or not text.endswith("}"):
        return StrategySpecValidation(False, None, ("strategy_spec_must_be_json_only",))
    try:
        payload = json.loads(
            text,
            parse_constant=reject_non_finite_json,
            parse_float=parse_finite_json_float,
        )
    except (json.JSONDecodeError, NonFiniteJsonNumberError):
        return StrategySpecValidation(False, None, ("strategy_spec_invalid_json",))
    if not isinstance(payload, dict):
        return StrategySpecValidation(False, None, ("strategy_spec_root_must_be_object",))
    return validate_strategy_spec(payload)


def validate_strategy_spec(payload: Mapping[str, JsonValue]) -> StrategySpecValidation:
    reasons = schema_rejection_reasons(payload)
    warnings: list[str] = []
    strategy_id = _string(payload, "strategy_id", reasons)
    version = _string(payload, "version", reasons)
    description = _optional_string(payload, "description")
    strategy_family = _strategy_family(payload.get("strategy_family"), reasons)
    research_basis = _research_basis(payload.get("research_basis"), reasons)
    signals = _signals(payload.get("signals"), reasons)
    entry_rule = _entry_rule(payload.get("entry_rule"), reasons)
    exit_rule = _exit_rule(payload.get("exit_rule"), reasons)
    position_sizing = _position_sizing(payload.get("position_sizing"), reasons)
    risk_controls = _risk_controls(payload.get("risk_controls"), reasons)
    created_at = _metadata_created_at(payload.get("metadata"), reasons)
    _validate_signal_weight_sum(signals, reasons)
    if reasons:
        return StrategySpecValidation(False, None, tuple(reasons), tuple(warnings))
    return StrategySpecValidation(
        True,
        StrategySpec(
            strategy_id,
            version,
            strategy_family,
            description,
            research_basis,
            tuple(signals),
            entry_rule,
            exit_rule,
            position_sizing,
            risk_controls,
            created_at,
            deepcopy(dict(payload)),
        ),
        (),
        tuple(warnings),
    )


def _string(payload: Mapping[str, JsonValue], key: str, reasons: list[str]) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    reasons.append(f"{key}_required")
    return ""


def _optional_string(payload: Mapping[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _object(value: JsonValue | None) -> Mapping[str, JsonValue] | None:
    return value if isinstance(value, dict) else None


def _string_tuple(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _strategy_family(value: JsonValue | None, reasons: list[str]) -> StrategyFamily:
    if not isinstance(value, str):
        reasons.append("strategy_family_required")
        return StrategyFamily.ENSEMBLE
    try:
        return StrategyFamily(value)
    except ValueError:
        reasons.append("strategy_family_not_allowed")
        return StrategyFamily.ENSEMBLE


def _research_basis(value: JsonValue | None, reasons: list[str]) -> ResearchBasis:
    data = _object(value)
    if data is None:
        reasons.append("research_basis_required")
        return ResearchBasis("", (), (), "")
    provider = data.get("provider")
    research_ids = _string_tuple(data.get("research_ids"))
    source_ids = _string_tuple(data.get("source_ids"))
    if provider != "insane_search":
        reasons.append("research_basis_provider_must_be_insane_search")
    if not research_ids:
        reasons.append("research_basis_research_ids_required")
    if not source_ids:
        reasons.append("research_basis_source_ids_required")
    return ResearchBasis(
        provider=provider if isinstance(provider, str) else "",
        research_ids=research_ids,
        source_ids=source_ids,
        summary=_optional_string(data, "summary"),
    )


def _signals(value: JsonValue | None, reasons: list[str]) -> list[SignalSpec]:
    if not isinstance(value, list) or not value:
        reasons.append("signals_required")
        return []
    signals: list[SignalSpec] = []
    for item in value:
        data = _object(item)
        if data is None:
            reasons.append("signal_must_be_object")
            continue
        parsed = _signal_from_object(data, reasons)
        if parsed is not None:
            signals.append(parsed)
    return signals


def _signal_from_object(
    data: Mapping[str, JsonValue],
    reasons: list[str],
) -> SignalSpec | None:
    signal_type = data.get("type")
    weight = data.get("weight")
    if not isinstance(signal_type, str):
        reasons.append("signal_type_required")
        return None
    try:
        parsed_signal_type = SignalType(signal_type)
    except ValueError:
        reasons.append("signal_type_not_allowed")
        return None
    if not is_json_number(weight):
        reasons.append("signal_weight_required")
        return None
    parameters = signal_parameters(data, reasons)
    return SignalSpec(parsed_signal_type, float(weight), parameters)


def _entry_rule(value: JsonValue | None, reasons: list[str]) -> EntryRule:
    data = _object(value)
    if data is None:
        reasons.append("entry_rule_required")
        return EntryRule("", 0.0, 0)
    threshold = data.get("threshold")
    top_n = data.get("top_n")
    if not is_json_number(threshold) or not 0 <= threshold <= 1:
        reasons.append("entry_rule_threshold_out_of_range")
    if not is_json_int(top_n) or top_n < 1:
        reasons.append("entry_rule_top_n_must_be_positive")
    return EntryRule(
        _optional_string(data, "type"),
        _float_or_zero(threshold),
        _int_or_zero(top_n),
    )


def _exit_rule(value: JsonValue | None, reasons: list[str]) -> ExitRule:
    data = _object(value)
    if data is None:
        reasons.append("exit_rule_required")
        return ExitRule("", 0.0, "", 0.0, False, 0)
    stop = data.get("stop_loss_atr_multiple")
    take = data.get("take_profit_atr_multiple")
    holding = data.get("max_holding_days")
    if not is_json_number(stop) or stop <= 0:
        reasons.append("stop_loss_atr_multiple_must_be_positive")
    if not is_json_number(take) or take <= 0:
        reasons.append("take_profit_atr_multiple_must_be_positive")
    if not is_json_int(holding) or holding < 1:
        reasons.append("max_holding_days_must_be_positive")
    return ExitRule(
        _optional_string(data, "stop_loss_mode"),
        _float_or_zero(stop),
        _optional_string(data, "take_profit_mode"),
        _float_or_zero(take),
        bool_field(data, "trailing_stop", reasons, False),
        _int_or_zero(holding),
    )


def _position_sizing(value: JsonValue | None, reasons: list[str]) -> PositionSizingSpec:
    data = _object(value)
    if data is None:
        reasons.append("position_sizing_required")
        return PositionSizingSpec("", 0.0, False, 0.0)
    risk = data.get("risk_per_trade_pct")
    max_single = data.get("max_single_position_pct")
    if not is_json_number(risk) or risk <= 0:
        reasons.append("risk_per_trade_pct_must_be_positive")
    if not is_json_number(max_single) or not 0 < max_single <= 1:
        reasons.append("max_single_position_pct_out_of_range")
    return PositionSizingSpec(
        _optional_string(data, "method"),
        _float_or_zero(risk),
        bool_field(data, "confidence_adjusted", reasons, False),
        _float_or_zero(max_single),
    )


def _risk_controls(value: JsonValue | None, reasons: list[str]) -> RiskControls:
    data = _object(value)
    if data is None:
        reasons.append("risk_controls_required")
        return RiskControls(True, True, True, True, True)
    return RiskControls(
        bool_field(data, "use_kill_switch", reasons, True),
        bool_field(data, "block_if_data_stale", reasons, True),
        bool_field(data, "block_if_spread_abnormal", reasons, True),
        bool_field(data, "block_if_daily_loss_limit", reasons, True),
        bool_field(data, "block_before_market_close", reasons, True),
    )


def _metadata_created_at(value: JsonValue | None, reasons: list[str]) -> str:
    data = _object(value)
    if data is None:
        reasons.append("metadata_required")
        return ""
    created_at = data.get("created_at")
    if not isinstance(created_at, str):
        reasons.append("metadata_created_at_required")
        return ""
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        reasons.append("metadata_created_at_invalid")
    return created_at


def _validate_signal_weight_sum(signals: list[SignalSpec], reasons: list[str]) -> None:
    if not signals:
        return
    total = sum(signal.weight for signal in signals)
    if not 0.99 <= total <= 1.01:
        reasons.append("signal_weight_sum_out_of_range")


def _float_or_zero(value: JsonValue | None) -> float:
    return float(value) if is_json_number(value) else 0.0


def _int_or_zero(value: JsonValue | None) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
