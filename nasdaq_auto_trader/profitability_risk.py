from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite

from .backtest_costs import BacktestCosts
from .models import AccountSnapshot, Action, OrderRequest, Position, TradeDecision
from .profitability_strategy import ProfitabilityStrategy
from .risk import RiskConfig, RiskManager


@dataclass(frozen=True, slots=True)
class EntryConstraintRecord:
    timestamp: str
    symbol: str
    action: Action
    buy_score: int | None
    sell_score: int | None
    entry_condition_met: bool
    first_reason: str
    blocking_conditions: tuple[str, ...]
    planned_qty: int
    risk_only_qty: int
    planned_risk: float | None
    initial_stop: float | None
    risk_budget: float
    price: float
    one_share_cost: float
    required_position_pct: float | None
    minimum_equity_usd: float | None
    portfolio_check: str = "engine_submission_and_fill"


@dataclass(frozen=True, slots=True)
class AcceptedOrder:
    timestamp: str
    symbol: str
    qty: int
    price: float
    planned_risk: float


class ProfitabilityRisk(RiskManager):
    """Mutable offline decision ledger; aggregate risk remains an execution-book gate."""

    def __init__(self, strategy: ProfitabilityStrategy, costs: BacktestCosts, risk_pct: float) -> None:
        super().__init__(RiskConfig(max_position_pct=0.5, min_cash_buffer_pct=0.05,
                                    min_order_notional=0, max_order_notional=35,
                                    risk_per_trade_pct=risk_pct, order_qty=1,
                                    max_position_qty=1, allow_additional_buy=False))
        self.strategy: ProfitabilityStrategy = strategy
        self.costs: BacktestCosts = costs
        self.timestamp: str = ""
        self.day: str = ""
        self.previous_equity: float = 0.0
        self.day_start_equity: float = 0.0
        self.day_halted: bool = False
        self.records: list[EntryConstraintRecord] = []
        self.accepted_orders: list[AcceptedOrder] = []

    def build_order(
        self, decision: TradeDecision, account: AccountSnapshot,
        position: Position | None, latest_price: float,
    ) -> OrderRequest | None:
        day = self.timestamp[:10]
        if day != self.day:
            self.day_start_equity = self.previous_equity or account.equity
            self.day, self.day_halted = day, False
        self.previous_equity = account.equity
        self.day_halted |= account.equity <= self.day_start_equity * 0.98
        if position is not None:
            return super().build_order(decision, account, position, latest_price)
        record = self._diagnose(decision, account, latest_price)
        self.records.append(record)
        if record.blocking_conditions or decision.action != "buy" or record.planned_risk is None:
            return None
        self.strategy.register_order_accepted(decision.symbol, self.timestamp)
        self.accepted_orders.append(AcceptedOrder(
            self.timestamp, decision.symbol, 1, latest_price, record.planned_risk,
        ))
        return OrderRequest(decision.symbol, "buy", type="limit", qty=1, limit_price=latest_price)

    def _diagnose(
        self, decision: TradeDecision, account: AccountSnapshot, price: float,
    ) -> EntryConstraintRecord:
        signal = next((row for row in reversed(self.strategy.records) if row.symbol == decision.symbol), None)
        buy_score = None if signal is None else signal.buy_score
        sell_score = None if signal is None else signal.sell_score
        entry_met = decision.action == "buy" or bool(signal and signal.entry_condition_met)
        stop = self.strategy.initial_stop_for(decision.symbol, price)
        valid_price = isfinite(price) and price > 0
        valid_account = all(isfinite(value) and value >= 0 for value in
                            (account.cash, account.equity, account.buying_power)) and account.equity > 0
        budget = account.equity * self.config.risk_per_trade_pct
        costs = (self.costs.fee(price) + self.costs.fee(stop)
                 + (price + stop) * self.costs.adverse_fraction) if stop is not None else 0.0
        planned = price - stop + costs if stop is not None else None
        conditions: list[str] = []
        data_reasons = {"no_data", "not_enough_data", "invalid_price", "completed_bar_unavailable_or_future"}
        if data_reasons.intersection(decision.reasons) or not valid_price or not valid_account:
            conditions.append("data_or_account_unavailable")
        if not entry_met:
            conditions.append("no_buy_signal")
        if sell_score is not None and sell_score >= self.strategy.config.sell_score and entry_met:
            conditions.append("conflicting_entry_exit_signal")
        if signal is not None and signal.duplicate_general_evaluation:
            conditions.append("completed_bar_already_evaluated")
        if self.day_halted:
            conditions.append("daily_loss_buy_halt")
        if stop is None:
            conditions.append("invalid_initial_stop_or_atr")
        if planned is not None and planned > budget + 1e-10:
            conditions.append("trade_risk_budget")
        fee = self.costs.fee(price) if valid_price else 0.0
        if valid_price and valid_account:
            after_fee = account.equity - fee
            if price > after_fee * 0.5 + 1e-10:
                conditions.append("symbol_position_limit")
            used = account.equity - account.cash
            if used + price > after_fee * 0.5 + 1e-10:
                conditions.append("total_exposure_limit")
            if price > 35 + 1e-10:
                conditions.append("order_notional_limit")
            if price + fee > account.buying_power + 1e-10:
                conditions.append("buying_power_limit")
            if price + fee > account.cash - account.equity * 0.05 + 1e-10:
                conditions.append("cash_with_costs")
            if not self.costs.valid_qty(1):
                conditions.append("integer_quantity_step")
        if decision.action == "buy" and (decision.risk_per_share is None
                or not isfinite(decision.risk_per_share)
                or (planned is not None and decision.risk_per_share + 1e-10 < planned)):
            conditions.append("missing_cost_inclusive_risk")
        risk_qty = (floor(budget / planned + 1e-10)
                    if planned is not None and planned > 0 and valid_account else 0)
        required_pct = price / (account.equity - fee) if valid_price and account.equity > fee else None
        minimum_equity = (max(price / 0.5 + fee, planned / self.config.risk_per_trade_pct,
                              (price + fee) / 0.95)
                          if planned is not None and valid_price else None)
        upstream = decision.reasons[-1] if decision.reasons else ""
        first = conditions[0] if conditions else "accepted"
        if upstream in {"completed_bar_already_evaluated", "conflicting_entry_exit_signal"}:
            first = upstream
        if upstream in {"invalid_entry_atr", "entry_stop_outside_bounds"}:
            first = "invalid_initial_stop_or_atr"
        return EntryConstraintRecord(
            self.timestamp, decision.symbol, decision.action, buy_score, sell_score, entry_met,
            first, tuple(conditions),
            int(not conditions and decision.action == "buy"), risk_qty, planned, stop,
            budget, price, costs, required_pct, minimum_equity,
        )
