from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Literal, TypeAlias

from .backtest import Backtester
from .backtest_costs import BacktestCosts
from .entry_comparison_metrics import entry_outcome, monthly_rows
from .entry_comparison_risk import MatchedEntryRisk
from .entry_policy_experiment import EntryPolicyStrategy
from .exit_experiment import EvaluationSplit, validate_daily_bars
from .exit_experiment_config import CostScenario, ExperimentInputError
from .exit_experiment_metrics import FxPoint, fx_at, summarize
from .models import Bar, Position, TradeDecision
from .strategy_config import StrategyConfig

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


class EntryEvaluation:
    def __init__(
        self,
        inner: EntryPolicyStrategy,
        risk: MatchedEntryRisk,
        split: EvaluationSplit,
        costs: BacktestCosts,
    ) -> None:
        self.inner, self.risk, self.split, self.costs = inner, risk, split, costs

    def decide(
        self, symbol: str, bars: list[Bar], position: Position | None
    ) -> TradeDecision:
        self.risk.timestamp = bars[-1].timestamp
        if bars[-1].timestamp < self.split.start:
            return TradeDecision(
                symbol, "hold", 0, bars[-1].close, ["warmup_no_orders"]
            )
        decision = self.inner.decide(symbol, bars, position)
        if decision.action != "buy" or decision.risk_per_share is None:
            return decision
        stop = max(0, decision.latest_price - decision.risk_per_share)
        cost = self.costs.fee(decision.latest_price) + self.costs.fee(stop)
        cost += (decision.latest_price + stop) * self.costs.adverse_fraction
        return replace(decision, risk_per_share=decision.risk_per_share + cost)


def load_entry_profile(path: Path) -> StrategyConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("dry_run") is not True or raw.get("broker") != "offline_csv":
        raise ExperimentInputError("entry comparison requires offline_csv dry_run=true")
    if raw.get("policies") != ["A", "B", "C"]:
        raise ExperimentInputError("only frozen A/B/C policies are permitted")
    expected_risk = {
        "order_qty": 1,
        "max_position_qty": 1,
        "max_position_pct": 0.5,
        "min_cash_buffer_pct": 0.05,
        "risk_per_trade_pct": 0.01,
        "allow_additional_buy": False,
    }
    if raw.get("risk") != expected_risk or any(
        type(raw["risk"][key]) is not type(value)
        for key, value in expected_risk.items()
    ):
        raise ExperimentInputError(
            "common risk must match the prespecified 1% one-share limits"
        )
    expected_limits = {
        "max_total_exposure_pct": 0.5,
        "max_automatic_buy_usd": 35,
        "daily_loss_stop_pct": 0.02,
        "starting_krw": 80000,
    }
    if raw.get("limits") != expected_limits or any(
        type(raw["limits"][key]) is not type(value)
        for key, value in expected_limits.items()
    ):
        raise ExperimentInputError("common capital and limits must remain frozen")
    expected_strategy = StrategyConfig(
        sma_fast=5,
        sma_slow=20,
        ema_fast=5,
        ema_slow=20,
        long_sma=20,
        stop_loss_pct=0.03,
        take_profit_pct=0.05,
    )
    config = StrategyConfig(**raw["strategy"])
    if config != expected_strategy:
        raise ExperimentInputError(
            "entry-only comparison cannot change strategy or exit parameters"
        )
    return config


def _write_rows(path: Path, rows: list[dict[str, JsonValue]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def run_entry_suite(
    config: StrategyConfig,
    bars: dict[str, list[Bar]],
    splits: tuple[EvaluationSplit, ...],
    output: Path,
    costs: tuple[CostScenario, ...],
    *,
    fx_rate: float,
    manifest: dict[str, JsonValue],
    fx_history: tuple[FxPoint, ...] = (),
    operations_monthly_krw: float | None = None,
) -> None:
    validate_daily_bars(bars)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ExperimentInputError(
            "output must be an empty directory; existing files cannot be overwritten"
        )
    policies: tuple[Literal["A", "B", "C"], ...] = ("A", "B", "C")
    protocol = {
        "strategy": asdict(config),
        "policies": policies,
        "common_risk_pct": 0.01,
        "starting_krw": 80000,
        "quantity": 1,
        "single_and_total_exposure_pct": 0.5,
        "cash_buffer_pct": 0.05,
        "max_order_usd": 35,
        "daily_new_buy_loss_halt_pct": 0.02,
        "historical_minimum_risk_override_5pct_included": False,
        "costs": [asdict(cost) for cost in costs],
        "splits": [asdict(split) for split in splits],
        "fx_rate": fx_rate,
        "operations_monthly_krw": operations_monthly_krw,
        "scope": "A is a matched-risk forced-entry proxy, not exact historical operating strategy",
        "fill_model": "completed daily close signal; subsequent daily limit touch or market open fill",
        "selection": "fixed historical-trade case cohort; symbol alphabetical processing; SPY separate control",
        "data_manifest": manifest,
    }
    protocol["protocol_sha256"] = hashlib.sha256(
        json.dumps(protocol, sort_keys=True).encode()
    ).hexdigest()
    (output / "protocol.json").write_text(
        json.dumps(protocol, indent=2), encoding="utf-8"
    )
    tables: dict[str, list[dict[str, JsonValue]]] = {
        name: []
        for name in (
            "summary",
            "monthly",
            "fills",
            "reasons",
            "equity",
            "entry_skips",
            "order_rejections",
            "decisions",
        )
    }
    for split in splits:
        prefix = {
            symbol: [bar for bar in history if bar.timestamp <= split.end]
            for symbol, history in bars.items()
        }
        split_fx = fx_at(split.start, fx_rate, fx_history)
        for policy in policies:
            for scenario in costs:
                cost = BacktestCosts(
                    scenario.commission_pct,
                    scenario.minimum_commission,
                    scenario.spread_bps,
                    scenario.slippage_bps,
                    1,
                )
                strategy = EntryPolicyStrategy(config, policy)
                risk = MatchedEntryRisk(strategy, cost)
                adapter = EntryEvaluation(strategy, risk, split, cost)
                result = Backtester(
                    adapter,
                    risk,
                    costs=cost,
                    max_trade_risk_pct=0.01,
                    max_total_position_pct=0.5,
                    fill_observer=strategy,
                    risk_includes_costs=True,
                ).run(prefix, starting_cash=80000 / split_fx)
                curve = tuple(
                    point
                    for point in result.equity_curve
                    if point.timestamp >= split.start
                )
                evaluated = replace(result, equity_curve=curve)
                performance = summarize(
                    evaluated,
                    fx_rate=split_fx,
                    fx_history=fx_history,
                    operations_monthly_krw=operations_monthly_krw,
                )
                key = {
                    "split": split.name,
                    "policy": policy,
                    "cost_scenario": scenario.name,
                    "common_risk_pct": 0.01,
                }
                tables["summary"].append(
                    key
                    | asdict(performance.summary)
                    | asdict(entry_outcome(evaluated, strategy, performance, split))
                )
                tables["monthly"].extend(
                    key | row for row in monthly_rows(performance, split)
                )
                for name, records in (
                    ("fills", result.trades),
                    ("reasons", performance.reasons),
                    ("equity", curve),
                    ("entry_skips", risk.skips),
                    ("order_rejections", result.rejections),
                    ("decisions", strategy.records),
                ):
                    tables[name].extend(key | asdict(record) for record in records)
    for name, rows in tables.items():
        _write_rows(output / f"{name}.csv", rows)
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
