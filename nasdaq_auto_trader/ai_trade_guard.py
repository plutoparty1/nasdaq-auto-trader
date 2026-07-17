"""Final safety checks for AI recommendations before order creation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import TypedDict, assert_never

from .ai_decision_schema import AITradeRecommendation
from .config_manager import (
    TradingSessionState,
    TradingSettings,
    validate_order_against_settings,
)
from .models import AccountSnapshot, OrderRequest, Position


class AITradeGuardBlockedResponse(TypedDict):
    status: str
    reason: str
    ai_guard: bool
    ai_recommendation: dict[str, str | int | float]


@dataclass(frozen=True, slots=True)
class AITradeGuardResult:
    """Order guard outcome for one AI recommendation."""

    order: OrderRequest | None
    response: dict | None

    @property
    def allowed(self) -> bool:
        return self.order is not None and self.response is None


def guard_ai_recommendation(
    recommendation: AITradeRecommendation,
    settings: TradingSettings,
    account: AccountSnapshot,
    position: Position | None,
    session_state: TradingSessionState,
    now: datetime,
    mode: str,
    latest_price: float,
) -> AITradeGuardResult:
    """Return an order only when every AI-specific and existing guard passes."""

    block_reason = _ai_block_reason(
        recommendation,
        settings,
        account,
        position,
        latest_price,
        mode,
    )
    if block_reason is not None:
        return AITradeGuardResult(
            None,
            _blocked_response(block_reason, recommendation),
        )

    match recommendation.action:
        case "buy":
            order = OrderRequest(
                symbol=recommendation.ticker,
                side="buy",
                type="limit",
                qty=float(recommendation.order_qty),
                limit_price=latest_price,
            )
        case "sell":
            order = OrderRequest(
                symbol=recommendation.ticker,
                side="sell",
                qty=float(recommendation.order_qty),
            )
        case "hold" | "skip":
            return AITradeGuardResult(
                None,
                _blocked_response(f"ai_{recommendation.action}", recommendation),
            )
        case _:
            assert_never(recommendation.action)

    existing_guard = validate_order_against_settings(
        order,
        account,
        position,
        settings,
        session_state,
        now,
        mode,
    )
    if existing_guard is not None:
        existing_guard = {
            **existing_guard,
            "ai_guard": True,
            "ai_recommendation": recommendation.to_dict(),
        }
        return AITradeGuardResult(None, existing_guard)

    return AITradeGuardResult(order, None)


def _ai_block_reason(
    recommendation: AITradeRecommendation,
    settings: TradingSettings,
    account: AccountSnapshot,
    position: Position | None,
    latest_price: float,
    mode: str,
) -> str | None:
    if recommendation.confidence < settings.ai_min_confidence:
        return "ai_confidence_below_minimum"
    if recommendation.order_qty > settings.ai_max_order_qty:
        return "ai_order_qty_exceeds_ai_max"
    if settings.ai_recommend_only:
        return "ai_recommend_only"
    if settings.require_confirm_after_ai:
        return "ai_confirmation_required"
    if settings.dry_run or mode == "dry_run":
        return "dry_run_blocks_ai_order"
    if not settings.live_trading:
        return "live_trading_disabled"

    position_qty = position.qty if position is not None else 0
    match recommendation.action:
        case "buy":
            if settings.sell_only:
                return "sell_only_mode"
            if position_qty > 0 and not settings.allow_additional_buy:
                return "additional_buy_disabled"
            if position_qty + recommendation.order_qty > settings.max_position_qty:
                return "max_position_qty_exceeded"
            if not all(
                isfinite(value)
                for value in (latest_price, account.cash, account.buying_power)
            ):
                return "cash_or_price_unavailable"
            if latest_price <= 0:
                return "latest_price_missing"
            required_cash = latest_price * recommendation.order_qty
            if account.cash < settings.min_cash_to_buy:
                return "min_cash_to_buy_not_met"
            if account.cash < required_cash:
                return "deposited_cash_insufficient"
            if account.buying_power < required_cash:
                return "buying_power_insufficient"
        case "sell":
            if position_qty <= 0:
                return "sell_position_missing"
            if recommendation.order_qty > position_qty:
                return "sell_qty_exceeds_position"
        case "hold" | "skip":
            return f"ai_{recommendation.action}"
        case _:
            assert_never(recommendation.action)

    return "ai_direct_order_disabled"


def _blocked_response(
    reason: str,
    recommendation: AITradeRecommendation,
) -> AITradeGuardBlockedResponse:
    return {
        "status": "blocked",
        "reason": reason,
        "ai_guard": True,
        "ai_recommendation": recommendation.to_dict(),
    }
