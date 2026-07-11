from __future__ import annotations

from collections.abc import Mapping

from .registry_models import StrategyRecord, StrategyStatus
from .strategy_schema import ResearchBasis
from .types import JsonValue


def record_from_json(payload: Mapping[str, JsonValue]) -> StrategyRecord | None:
    basis = payload.get("research_basis")
    research_basis = _basis_from_json(basis if isinstance(basis, dict) else {})
    status = _strategy_status(payload.get("status"))
    if status is None:
        return None
    return StrategyRecord(
        strategy_id=_string(payload.get("strategy_id")),
        version=_string(payload.get("version")),
        status=status,
        allowed_for_live=payload.get("allowed_for_live") is True,
        manual_approval=payload.get("manual_approval") is True,
        research_basis=research_basis,
        score=_float_or_zero(payload.get("score")),
        rejection_reasons=_string_tuple(payload.get("rejection_reasons")),
    )


def _basis_from_json(payload: Mapping[str, JsonValue]) -> ResearchBasis:
    return ResearchBasis(
        provider=_string(payload.get("provider")),
        research_ids=_string_tuple(payload.get("research_ids")),
        source_ids=_string_tuple(payload.get("source_ids")),
        summary=_string(payload.get("summary")),
    )


def _string(value: JsonValue | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_tuple(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _strategy_status(value: JsonValue | None) -> StrategyStatus | None:
    text = _string(value)
    if not text:
        return StrategyStatus.REJECTED
    try:
        return StrategyStatus(text)
    except ValueError:
        return None


def _float_or_zero(value: JsonValue | None) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0
