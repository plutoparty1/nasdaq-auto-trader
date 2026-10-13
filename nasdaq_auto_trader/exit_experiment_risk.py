"""Offline-only integer sizing; this adapter never constructs a broker."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from typing import Literal

from .backtest_costs import BacktestCosts
from .models import AccountSnapshot, OrderRequest, Position, TradeDecision
from .risk import RiskConfig, RiskManager


@dataclass(frozen=True, slots=True)
class EntrySkip:
    timestamp: str
    symbol: str
    reason: str
    price: float
    planned_one_share_loss: float
    budget: float


class ExperimentRiskManager(RiskManager):
    """Mutable offline account-month state and an auditable rejected-entry ledger."""

    def __init__(
        self,
        *,
        risk_pct: float,
        sizing: Literal["one_share", "risk_sized"],
        max_position_pct: float,
        cash_buffer_pct: float,
        monthly_loss_stop_pct: float,
        costs: BacktestCosts | None = None,
        max_total_position_pct: float = 1.0,
    ) -> None:
        super().__init__(
            RiskConfig(
                max_position_pct=max_position_pct,
                min_cash_buffer_pct=cash_buffer_pct,
                min_order_notional=0,
                risk_per_trade_pct=risk_pct,
                allow_additional_buy=False,
            )
        )
        self.max_total_position_pct = max_total_position_pct
        self.costs = costs or BacktestCosts(quantity_step=1)
        self.sizing = sizing
        self.monthly_loss_stop_pct = monthly_loss_stop_pct
        self.timestamp = ""
        self.month = ""
        self.month_open_equity = 0.0
        self.previous_equity = 0.0
        self.month_halted = False
        self.skips: list[EntrySkip] = []

    def build_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None:
        month = self.timestamp[:7]
        if month != self.month:
            self.month_open_equity = (
                self.previous_equity if self.month else account.equity
            )
            self.month = month
            self.month_halted = False
        self.previous_equity = account.equity
        if account.equity <= self.month_open_equity * (1 - self.monthly_loss_stop_pct):
            self.month_halted = True
        if decision.action != "buy":
            return super().build_order(decision, account, position, latest_price)
        distance = decision.risk_per_share or 0.0
        budget = account.equity * self.config.risk_per_trade_pct
        reason = ""
        if self.month_halted:
            reason = "monthly_loss_buy_halt"
        elif position is not None:
            reason = "additional_buy_disabled_in_comparison"
        elif not all(
            isfinite(value) and value > 0 for value in (distance, latest_price, budget)
        ):
            reason = "invalid_initial_stop_or_price"
        elif distance > budget + 1e-12:
            reason = "one_share_exceeds_risk_budget"
        if reason:
            self.skips.append(
                EntrySkip(
                    self.timestamp,
                    decision.symbol,
                    reason,
                    latest_price,
                    distance,
                    budget,
                )
            )
            return None
        available = min(
            account.buying_power,
            max(0.0, account.cash - account.equity * self.config.min_cash_buffer_pct),
            account.equity * self.config.max_position_pct,
            max(
                0.0,
                account.equity * self.max_total_position_pct
                - (account.equity - account.cash),
            ),
        )
        qty = min(
            floor(self.costs.affordable_qty(available, latest_price)),
            floor(budget / distance + 1e-12),
        )
        if self.sizing == "one_share":
            qty = min(qty, 1)
        if qty <= 0:
            self.skips.append(
                EntrySkip(
                    self.timestamp,
                    decision.symbol,
                    "one_share_exceeds_cash_or_position_limit",
                    latest_price,
                    distance,
                    budget,
                )
            )
            return None
        return OrderRequest(
            decision.symbol,
            "buy",
            type="limit",
            qty=float(qty),
            limit_price=latest_price,
        )
