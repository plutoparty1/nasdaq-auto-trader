"""Passive risk diagnostics of the unchanged historical A/B/C simulator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path

from .backtest import Backtester
from .backtest_costs import BacktestCosts
from .backtest_types import BacktestResult
from .entry_comparison import EntryEvaluation, JsonValue, _write_rows
from .entry_comparison_risk import ComparisonSkip, MatchedEntryRisk
from .entry_policy_experiment import EntryPolicyStrategy
from .entry_policy_experiment_models import EntryDecisionRecord
from .exit_experiment import EvaluationSplit, validate_daily_bars
from .exit_experiment_config import CostScenario, ExperimentInputError
from .exit_experiment_metrics import FxPoint, fx_at
from .models import AccountSnapshot, Bar, OrderRequest, Position, TradeDecision
from .strategy_config import StrategyConfig


@dataclass(frozen=True, slots=True)
class LegacyRun:
    split: str
    policy: str
    cost_scenario: str
    result: BacktestResult
    decisions: tuple[EntryDecisionRecord, ...]
    skips: tuple[ComparisonSkip, ...]


@dataclass(frozen=True, slots=True)
class LegacyDiagnostic:
    timestamp: str
    symbol: str
    base_action: str
    final_action: str
    first_reason: str
    order_built: bool
    price: float
    equity: float
    available_cash: float
    buying_power: float
    risk_budget: float
    planned_one_share_risk: float | None
    risk_quantity_before_integer_rounding: float | None
    fixed_order_qty: int
    quantity_step: int
    minimum_order_notional: float
    portfolio_risk_limit_applied: bool
    no_buy_signal: bool
    buy_score_insufficient: bool
    simultaneous_sell_signal: bool
    duplicate_signal: bool
    risk_budget_exceeded: bool | None
    single_position_limit: bool
    total_exposure_limit: bool
    max_order_notional_limit: bool
    cash_buffer_and_cost_limit: bool
    buying_power_limit: bool
    integer_one_share_risk_limit: bool | None
    daily_loss_halt: bool
    insufficient_data: bool


@dataclass(frozen=True, slots=True)
class ShadowDecision:
    record: EntryDecisionRecord
    planned_risk: float | None


class DiagnosticRisk(MatchedEntryRisk):
    """Accumulate shadow constraints after the original risk decision returns."""

    def __init__(self, strategy: EntryPolicyStrategy, costs: BacktestCosts) -> None:
        super().__init__(strategy, costs)
        self.shadow: ShadowDecision | None = None
        self.diagnostics: list[LegacyDiagnostic] = []

    def build_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None:
        previous_skips = len(self.skips)
        order = super().build_order(decision, account, position, latest_price)
        if self.shadow is None or (position is not None and position.qty > 0):
            return order
        record, planned = self.shadow.record, self.shadow.planned_risk
        first = record.reason
        if len(self.skips) > previous_skips:
            first = self.skips[-1].reason
        if order is not None:
            first = "order_built"
        price = record.indicator_price or latest_price
        valid_price = isfinite(price) and price > 0
        budget = account.equity * 0.01
        exceeded = None if planned is None else planned > budget
        self.diagnostics.append(
            LegacyDiagnostic(
                timestamp=self.timestamp,
                symbol=decision.symbol,
                base_action=record.base_action,
                final_action=decision.action,
                first_reason=first,
                order_built=order is not None,
                price=price,
                equity=account.equity,
                available_cash=account.cash,
                buying_power=account.buying_power,
                risk_budget=budget,
                planned_one_share_risk=planned,
                risk_quantity_before_integer_rounding=None
                if planned is None
                else budget / planned,
                fixed_order_qty=1,
                quantity_step=1,
                minimum_order_notional=0,
                portfolio_risk_limit_applied=False,
                no_buy_signal=record.base_action != "buy",
                buy_score_insufficient=record.buy_score is None
                or record.buy_score < self.strategy.config.buy_score,
                simultaneous_sell_signal=record.sell_score is not None
                and record.sell_score >= self.strategy.config.sell_score,
                duplicate_signal=record.duplicate_general_evaluation,
                risk_budget_exceeded=exceeded,
                single_position_limit=price > account.equity * 0.5,
                total_exposure_limit=account.equity - account.cash + price
                > account.equity * 0.5 + 1e-10,
                max_order_notional_limit=price > 35,
                cash_buffer_and_cost_limit=valid_price
                and self.costs.affordable_qty(
                    account.cash - account.equity * 0.05, price
                )
                < 1,
                buying_power_limit=price > account.buying_power,
                integer_one_share_risk_limit=exceeded,
                daily_loss_halt=self.day_halted,
                insufficient_data=record.buy_score is None
                or planned is None
                or not valid_price,
            )
        )
        return order


class DiagnosticEvaluation(EntryEvaluation):
    """Observe pre-risk decisions; shadow distance never feeds an actual order."""

    def __init__(
        self,
        inner: EntryPolicyStrategy,
        risk: DiagnosticRisk,
        split: EvaluationSplit,
        costs: BacktestCosts,
    ) -> None:
        super().__init__(inner, risk, split, costs)
        self.diagnostic_risk: DiagnosticRisk = risk

    def decide(
        self, symbol: str, bars: list[Bar], position: Position | None
    ) -> TradeDecision:
        self.diagnostic_risk.shadow = None
        decision = super().decide(symbol, bars, position)
        if bars[-1].timestamp < self.split.start:
            return decision
        record = self.inner.records[-1]
        distance = self.inner._risk_per_share(bars, bars[-1].close)
        planned = None
        if (
            record.buy_score is not None
            and distance is not None
            and isfinite(distance)
            and distance > 0
        ):
            stop = max(0, bars[-1].close - distance)
            planned = distance + self.costs.fee(bars[-1].close) + self.costs.fee(stop)
            planned += (bars[-1].close + stop) * self.costs.adverse_fraction
        self.diagnostic_risk.shadow = ShadowDecision(record, planned)
        return decision


def run_legacy_diagnostics(
    config: StrategyConfig,
    bars: Mapping[str, list[Bar]],
    splits: tuple[EvaluationSplit, ...],
    costs: tuple[CostScenario, ...],
    *,
    fx_rate: float,
    fx_history: tuple[FxPoint, ...],
    output: Path,
) -> tuple[LegacyRun, ...]:
    """Replay original 1% A/B/C and save all flat-entry mathematical constraints."""
    if output.exists() and any(output.iterdir()):
        raise ExperimentInputError("legacy diagnostics output must be empty")
    validate_daily_bars(dict(bars))
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, JsonValue]] = []
    runs: list[LegacyRun] = []
    for split in splits:
        prefix = {
            symbol: [bar for bar in history if bar.timestamp <= split.end]
            for symbol, history in bars.items()
        }
        for policy in ("A", "B", "C"):
            for scenario in costs:
                cost = BacktestCosts(
                    scenario.commission_pct,
                    scenario.minimum_commission,
                    scenario.spread_bps,
                    scenario.slippage_bps,
                    1,
                )
                strategy = EntryPolicyStrategy(config, policy)
                risk = DiagnosticRisk(strategy, cost)
                adapter = DiagnosticEvaluation(strategy, risk, split, cost)
                result = Backtester(
                    adapter,
                    risk,
                    costs=cost,
                    max_trade_risk_pct=0.01,
                    max_total_position_pct=0.5,
                    fill_observer=strategy,
                    risk_includes_costs=True,
                ).run(
                    prefix,
                    starting_cash=80000 / fx_at(split.start, fx_rate, fx_history),
                )
                runs.append(
                    LegacyRun(
                        split.name,
                        policy,
                        scenario.name,
                        result,
                        tuple(strategy.records),
                        tuple(risk.skips),
                    )
                )
                for record in risk.diagnostics:
                    rows.append(
                        {
                            "split": split.name,
                            "policy": policy,
                            "cost_scenario": scenario.name,
                            **asdict(record),
                        }
                    )
    _write_rows(output / "diagnostics.csv", rows)
    return tuple(runs)
