"""Strict schema for AI-generated trade recommendations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, Literal


AITradeAction = Literal["buy", "sell", "hold", "skip"]
AI_ACTIONS_BY_VALUE: Final[dict[str, AITradeAction]] = {
    "buy": "buy",
    "sell": "sell",
    "hold": "hold",
    "skip": "skip",
}

@dataclass(frozen=True, slots=True)
class AIDecisionSchemaError(ValueError):
    """Raised when an AI recommendation is unsafe or not valid JSON."""

    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class AITradeRecommendation:
    """A normalized AI recommendation after strict JSON validation."""

    action: AITradeAction
    ticker: str
    order_qty: int
    confidence: float
    reason: str
    risk: str

    def to_dict(self) -> dict[str, str | int | float]:
        return {
            "action": self.action,
            "ticker": self.ticker,
            "order_qty": self.order_qty,
            "confidence": self.confidence,
            "reason": self.reason,
            "risk": self.risk,
        }


def parse_ai_trade_recommendation(
    raw_response: str,
    candidate_tickers: list[str],
) -> AITradeRecommendation:
    """Parse and validate the exact JSON object returned by the AI provider."""

    if not isinstance(raw_response, str) or not raw_response.strip():
        raise AIDecisionSchemaError("AI response is empty")

    try:
        payload = json.loads(
            raw_response.strip(),
            parse_constant=_reject_non_finite_json,
        )
    except json.JSONDecodeError as exc:
        raise AIDecisionSchemaError(f"AI response is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise AIDecisionSchemaError("AI response must be a JSON object")

    required = {"action", "ticker", "order_qty", "confidence", "reason", "risk"}
    missing = sorted(required - set(payload))
    if missing:
        raise AIDecisionSchemaError(f"AI response missing required keys: {', '.join(missing)}")

    action = _parse_ai_action(str(payload["action"]).strip().lower())

    ticker = str(payload["ticker"]).strip().upper()
    candidates = {_normalize_ticker(item) for item in candidate_tickers}
    candidates.discard("")
    if not candidates:
        raise AIDecisionSchemaError("AI candidate ticker list is empty")
    if ticker not in candidates:
        raise AIDecisionSchemaError(f"AI ticker is outside candidate list: {ticker}")

    order_qty = payload["order_qty"]
    if isinstance(order_qty, bool) or not isinstance(order_qty, int):
        raise AIDecisionSchemaError("AI order_qty must be an integer")
    if order_qty < 1:
        raise AIDecisionSchemaError("AI order_qty must be >= 1")

    confidence = payload["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise AIDecisionSchemaError("AI confidence must be a number")
    confidence = float(confidence)
    if not (0 <= confidence <= 1):
        raise AIDecisionSchemaError("AI confidence must be between 0 and 1")

    reason = str(payload["reason"]).strip()
    risk = str(payload["risk"]).strip()
    if not reason:
        raise AIDecisionSchemaError("AI reason must not be empty")
    if not risk:
        raise AIDecisionSchemaError("AI risk must not be empty")

    return AITradeRecommendation(
        action=action,
        ticker=ticker,
        order_qty=order_qty,
        confidence=confidence,
        reason=reason,
        risk=risk,
    )


def _parse_ai_action(value: str) -> AITradeAction:
    try:
        return AI_ACTIONS_BY_VALUE[value]
    except KeyError as exc:
        raise AIDecisionSchemaError(f"AI action is not allowed: {value!r}") from exc


def _normalize_ticker(value: str) -> str:
    return str(value).strip().upper()


def _reject_non_finite_json(token: str) -> None:
    raise AIDecisionSchemaError(f"AI response contains non-finite JSON number: {token}")
