from __future__ import annotations

from dataclasses import dataclass

from .backtest_costs import BacktestCosts
from .entry_policy_experiment import EntryPolicyStrategy
from .models import AccountSnapshot, OrderRequest, Position, TradeDecision
from .risk import RiskConfig, RiskManager


@dataclass(frozen=True, slots=True)
class ComparisonSkip:
    timestamp: str
    symbol: str
    reason: str
    planned_one_share_risk: float
    risk_budget: float


class MatchedEntryRisk(RiskManager):
    def __init__(self, strategy: EntryPolicyStrategy, costs: BacktestCosts) -> None:
        super().__init__(
            RiskConfig(
                max_position_pct=0.5,
                min_cash_buffer_pct=0.05,
                min_order_notional=0,
                max_order_notional=35,
                risk_per_trade_pct=0.01,
                order_qty=1,
                max_position_qty=1,
                allow_additional_buy=False,
            )
        )
        self.strategy, self.costs = strategy, costs
        self.timestamp = ""
        self.day = ""
        self.day_start_equity = 0.0
        self.previous_equity = 0.0
        self.day_halted = False
        self.skips: list[ComparisonSkip] = []

    def build_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None:
        day = self.timestamp[:10]
        if day != self.day:
            self.day_start_equity = self.previous_equity or account.equity
            self.day, self.day_halted = day, False
        self.previous_equity = account.equity
        self.day_halted |= account.equity <= self.day_start_equity * 0.98
        if decision.action != "buy":
            return super().build_order(decision, account, position, latest_price)
        reason = ""
        if self.day_halted:
            reason = "daily_account_loss_buy_halt_2pct"
        elif (
            account.equity - account.cash + latest_price > account.equity * 0.5 + 1e-10
        ):
            reason = "total_exposure_limit_50pct"
        elif (
            self.costs.affordable_qty(
                account.cash - account.equity * 0.05, latest_price
            )
            < 1
        ):
            reason = "one_share_cash_and_cost_limit"
        order = (
            None
            if reason
            else super().build_order(decision, account, position, latest_price)
        )
        if order is None:
            self.skips.append(
                ComparisonSkip(
                    self.timestamp,
                    decision.symbol,
                    reason or "unchanged_quantity_price_or_risk_limit",
                    decision.risk_per_share or 0.0,
                    account.equity * 0.01,
                )
            )
        else:
            self.strategy.register_order_accepted(decision.symbol, self.timestamp)
        return order
