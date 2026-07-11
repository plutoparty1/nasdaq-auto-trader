from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from .ai_decision_schema import (
    AIDecisionSchemaError,
    AITradeAction,
    AITradeRecommendation,
    parse_ai_trade_recommendation,
)
from .ai_trading_supervisor import (
    SupervisorAction,
    SupervisorDecisionError,
    parse_supervisor_decision,
)


@dataclass(frozen=True, slots=True)
class SupervisorAdapterRequest:
    candidate_tickers: tuple[str, ...]
    deterministic_order_qty: int
    maximum_order_qty: int
    now: datetime
    maximum_age_seconds: int = 60


def parse_provider_recommendation(
    raw_response: str,
    request: SupervisorAdapterRequest,
) -> AITradeRecommendation:
    try:
        return parse_ai_trade_recommendation(
            raw_response,
            list(request.candidate_tickers),
        )
    except AIDecisionSchemaError as legacy_error:
        if not _has_supervisor_shape(raw_response):
            raise legacy_error
    return parse_supervisor_recommendation(raw_response, request)


def parse_supervisor_recommendation(
    raw_response: str,
    request: SupervisorAdapterRequest,
) -> AITradeRecommendation:
    try:
        decision = parse_supervisor_decision(
            raw_response,
            request.now,
            request.maximum_age_seconds,
        )
    except SupervisorDecisionError as exc:
        raise AIDecisionSchemaError(exc.reason) from exc
    if decision.symbol not in request.candidate_tickers:
        raise AIDecisionSchemaError("supervisor_symbol_outside_candidates")
    order_qty = max(
        1,
        min(request.deterministic_order_qty, request.maximum_order_qty),
    )
    return AITradeRecommendation(
        action=_legacy_action(decision.action),
        ticker=decision.symbol,
        order_qty=order_qty,
        confidence=decision.confidence,
        reason=decision.summary,
        risk=", ".join(decision.risk_flags) or "no_supervisor_risk_flags",
    )


def _legacy_action(action: SupervisorAction) -> AITradeAction:
    match action:
        case SupervisorAction.BUY:
            return "buy"
        case SupervisorAction.SELL | SupervisorAction.REDUCE | SupervisorAction.EXIT:
            return "sell"
        case SupervisorAction.HOLD:
            return "hold"
        case SupervisorAction.NO_TRADE:
            return "skip"
        case _ as unreachable:
            assert_never(unreachable)


def _has_supervisor_shape(raw_response: str) -> bool:
    try:
        payload = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    required_markers = {
        "signal_timestamp",
        "target_position_pct",
        "model_version",
        "market_regime",
    }
    return required_markers.issubset(payload)
