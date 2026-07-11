from __future__ import annotations

from typing import Literal, TypedDict


AIDecisionErrorCode = Literal["ai_provider_unavailable"]


class AIDecisionResultDict(TypedDict, total=False):
    status: str
    candidate_tickers: list[str]
    raw_response: str | None
    parse_success: bool
    recommendation: dict[str, str | int | float] | None
    error: str | None
    error_code: AIDecisionErrorCode
    attempts: int
    prompt: str
    final_status: str
    validation_passed: bool
    order_submitted: bool
    block_reason: str | int | float | bool | None


class MarketSummary(TypedDict, total=False):
    error: str
    latest_price: float
    change_pct: float
    volume: float
    rsi: float | None
    short_ma: float | None
    long_ma: float | None
    volatility_pct: float | None


class TradingAgentsRecommendationUnavailableError(RuntimeError):
    pass
