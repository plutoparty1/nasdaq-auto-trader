from __future__ import annotations

from dataclasses import dataclass

from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.strategies.base_strategy import TargetPosition


@dataclass(frozen=True, slots=True)
class PortfolioState:
    account_equity: float
    available_cash: float
    current_positions: dict[str, int]
    current_exposure: float
    daily_loss_limit_reached: bool = False


@dataclass(frozen=True, slots=True)
class SizingRequest:
    target: TargetPosition
    portfolio: PortfolioState
    current_price: float
    volatility: float = 0.0


@dataclass(frozen=True, slots=True)
class SizingResult:
    target_qty: int
    order_qty: int
    notional: float
    risk_amount: float
    sizing_reason: str
    blocked_reason: str


class PositionSizer:
    def __init__(self, config: AIQuantConfig | None = None) -> None:
        self.config = config or AIQuantConfig()

    def calculate(self, request: SizingRequest) -> SizingResult:
        if request.portfolio.daily_loss_limit_reached:
            return _blocked("daily_loss_limit_reached")
        if request.current_price <= 0:
            return _blocked("current_price_missing")
        if request.target.side == "sell":
            return self._sell_size(request)
        return self._buy_size(request)

    def _buy_size(self, request: SizingRequest) -> SizingResult:
        risk_per_share = abs(request.target.entry_price - request.target.stop_price)
        if risk_per_share <= 0:
            return _blocked("risk_per_share_missing")
        risk_amount = request.portfolio.account_equity * request.target.confidence * 0.005
        risk_qty = int(risk_amount / risk_per_share)
        cash_qty = int(request.portfolio.available_cash / request.current_price)
        current_symbol_value = (
            request.portfolio.current_positions.get(request.target.symbol, 0)
            * request.current_price
        )
        single_qty = int(
            (
                request.portfolio.account_equity * self.config.max_single_position_pct
                - current_symbol_value
            )
            / request.current_price
        )
        total_qty = int(
            (
                request.portfolio.account_equity * self.config.max_total_exposure_pct
                - request.portfolio.current_exposure
            )
            / request.current_price
        )
        notional_qty = int(self.config.max_order_notional / request.current_price)
        qty = max(min(risk_qty, cash_qty, single_qty, total_qty, notional_qty), 0)
        if qty < 1:
            return _blocked("sizing_limits_block_order")
        notional = qty * request.current_price
        if notional > request.portfolio.available_cash:
            return _blocked("available_cash_exceeded")
        return SizingResult(qty, qty, notional, risk_amount, "risk_and_exposure_capped", "")

    def _sell_size(self, request: SizingRequest) -> SizingResult:
        held_qty = request.portfolio.current_positions.get(request.target.symbol, 0)
        requested_qty = max(int(request.target.position_strength), 1)
        qty = min(held_qty, requested_qty)
        if qty < 1:
            return _blocked("sell_position_missing")
        return SizingResult(qty, qty, qty * request.current_price, 0.0, "sell_held_quantity", "")


def _blocked(reason: str) -> SizingResult:
    return SizingResult(0, 0, 0.0, 0.0, "", reason)
