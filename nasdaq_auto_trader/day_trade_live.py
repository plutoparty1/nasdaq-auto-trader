from __future__ import annotations

import re
from typing import Callable

from .day_trade_types import (
    DayTradePlan,
    LiveBuyConfirmation,
    LiveBuyPreview,
    LiveOrderSafetyError,
)


def assert_live_order_allowed(dry_run: bool, live_trading: bool) -> None:
    """Guard immediately before any future live order submission."""

    if dry_run:
        raise LiveOrderSafetyError("dry_run=True blocks live order submission")
    if not live_trading:
        raise LiveOrderSafetyError(
            "live_trading=True is required for live order submission"
        )


def build_live_buy_confirmation_phrase(plan: DayTradePlan) -> str:
    """Return the exact phrase required for a guarded live buy order."""

    preview = _live_buy_preview(plan)
    return (
        f"BUY {preview['ticker']} {_qty_text(preview['qty'])} "
        f"@ {preview['limit_price']:.4f}"
    )


def _evaluate_live_buy_confirmation(
    answer: str,
    preview: LiveBuyPreview,
    required_phrase: str,
    tolerance_pct: float,
) -> LiveBuyConfirmation:
    normalized = _normalize_confirmation_text(answer)
    result: LiveBuyConfirmation = {
        "accepted": False,
        "accepted_by": None,
        "reason": "confirmation_mismatch",
        "entered_confirmation": normalized,
        "entered_ticker": None,
        "entered_qty": None,
        "entered_limit_price": None,
        "current_limit_price": preview["limit_price"],
        "price_diff_pct": None,
        "tolerance_pct": tolerance_pct,
    }
    if normalized == required_phrase:
        result.update(
            {
                "accepted": True,
                "accepted_by": "exact_match",
                "reason": None,
                "entered_ticker": preview["ticker"],
                "entered_qty": preview["qty"],
                "entered_limit_price": preview["limit_price"],
                "price_diff_pct": 0.0,
            }
        )
        return result

    parsed = _parse_live_buy_confirmation(normalized)
    if parsed is None:
        result["reason"] = "confirmation_format_mismatch"
        return result

    result.update(
        {
            "entered_ticker": parsed["ticker"],
            "entered_qty": parsed["qty"],
            "entered_limit_price": parsed["limit_price"],
        }
    )
    if parsed["ticker"] != preview["ticker"]:
        result["reason"] = "confirmation_ticker_mismatch"
        return result
    if abs(parsed["qty"] - preview["qty"]) > 1e-8:
        result["reason"] = "confirmation_qty_mismatch"
        return result

    current_price = float(preview["limit_price"])
    entered_price = float(parsed["limit_price"])
    if current_price <= 0 or entered_price <= 0:
        result["reason"] = "confirmation_price_invalid"
        return result

    price_diff_pct = abs(entered_price - current_price) / current_price * 100
    result["price_diff_pct"] = round(price_diff_pct, 6)
    if price_diff_pct > tolerance_pct:
        result["reason"] = "confirmation_price_outside_tolerance"
        return result

    result.update(
        {
            "accepted": True,
            "accepted_by": "price_tolerance",
            "reason": None,
        }
    )
    return result


def _normalize_confirmation_text(value: str) -> str:
    return value.replace("\ufeff", "").strip()


def _parse_live_buy_confirmation(value: str) -> LiveBuyPreview | None:
    match = re.fullmatch(
        r"BUY\s+([A-Z0-9._-]+)\s+(\d+(?:\.\d+)?)\s+@\s+(\d+(?:\.\d+)?)",
        value.upper(),
    )
    if match is None:
        return None
    try:
        return {
            "ticker": match.group(1),
            "qty": float(match.group(2)),
            "limit_price": float(match.group(3)),
        }
    except ValueError:
        return None


def _live_buy_preview(plan: DayTradePlan) -> LiveBuyPreview:
    selected = plan.get("selected") or {}
    buy_order = plan.get("buy_order") or {}
    ticker = str(buy_order.get("symbol") or selected.get("symbol") or "").upper()
    qty = float(buy_order.get("qty") or 0)
    return {
        "stock_name": str(selected.get("name") or ticker),
        "ticker": ticker,
        "current_price": round(float(selected.get("last_price") or 0), 4),
        "limit_price": round(float(buy_order.get("limit_price") or 0), 4),
        "qty": qty,
        "estimated_amount": round(
            float(buy_order.get("estimated_required_amount") or 0),
            4,
        ),
        "buying_power": round(float(buy_order.get("buying_power") or 0), 4),
    }


def _print_live_buy_confirmation(
    preview: LiveBuyPreview,
    phrase: str,
    tolerance_pct: float,
    output: Callable[[str], None],
) -> None:
    output("LIVE ORDER FINAL CHECK")
    output(f"Stock name: {preview['stock_name']}")
    output(f"Ticker: {preview['ticker']}")
    output(f"Current price: {preview['current_price']:.4f} USD")
    output(f"Limit price: {preview['limit_price']:.4f} USD")
    output(f"Quantity: {_qty_text(preview['qty'])}")
    output(f"Estimated amount: {preview['estimated_amount']:.4f} USD")
    output(f"Buying power: {preview['buying_power']:.4f} USD")
    output(f"Required confirmation: {phrase}")
    output(f"Accepted price tolerance: {tolerance_pct:.2f}%")


def _qty_text(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)
