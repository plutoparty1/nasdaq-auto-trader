from __future__ import annotations

from math import floor, isfinite

from nasdaq_auto_trader.ai_quant_lab.strategy_schema import PositionSizingSpec


def backtest_position_quantity(
    sizing: PositionSizingSpec,
    position_strength: float,
    fill_price: float,
    risk_distance: float,
    portfolio_equity: float,
    available_cash: float,
) -> int:
    values = (
        position_strength,
        fill_price,
        risk_distance,
        portfolio_equity,
        available_cash,
    )
    if any(not isfinite(value) for value in values):
        return 0
    if fill_price <= 0 or risk_distance <= 0 or portfolio_equity <= 0:
        return 0
    position_limit = floor(
        portfolio_equity * sizing.max_single_position_pct / fill_price
    )
    risk_limit = floor(
        portfolio_equity * sizing.risk_per_trade_pct / risk_distance
    )
    cash_limit = floor(max(available_cash, 0.0) / fill_price)
    quantity = min(position_limit, risk_limit, cash_limit)
    if sizing.confidence_adjusted:
        quantity = floor(quantity * max(min(position_strength, 1.0), 0.0))
    return max(quantity, 0)
