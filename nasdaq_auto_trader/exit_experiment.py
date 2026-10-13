"""Controlled daily-bar exit experiments; no broker or live-settings dependencies."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from .backtest import Backtester, BacktestResult
from .backtest_costs import BacktestCosts
from .exit_experiment_config import (
    CostScenario,
    ExperimentInputError,
    ExperimentSettings,
)
from .exit_experiment_metrics import FxPoint, fx_at, summarize
from .exit_experiment_risk import ExperimentRiskManager
from .experimental_exit import ExperimentalExitStrategy
from .experimental_exit_models import ExitPolicy
from .models import Bar, Position, TradeDecision
from .strategy import TechnicalStrategy


@dataclass(frozen=True, slots=True)
class Candidate:
    name: str
    corrected: bool
    policy: ExitPolicy | None


@dataclass(frozen=True, slots=True)
class EvaluationSplit:
    name: str
    start: str
    end: str


def candidates(compare_entry_gate: bool = False) -> tuple[Candidate, ...]:
    path = Path(__file__).resolve().parents[1] / "experiments/early_exit/profiles.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("dry_run") is not True or raw.get("broker") != "offline_csv":
        raise ExperimentInputError("candidate profiles must be offline dry_run")
    if set(raw) != {"dry_run", "broker", "candidates"}:
        raise ExperimentInputError("unexpected candidate profile fields")
    for value in raw["candidates"]:
        if set(value) != {"name", "corrected", "policy"} or not isinstance(
            value["corrected"], bool
        ):
            raise ExperimentInputError(
                "candidate corrected must be boolean with exact profile fields"
            )
    result = tuple(
        Candidate(
            value["name"],
            value["corrected"],
            None if value["policy"] is None else ExitPolicy(**value["policy"]),
        )
        for value in raw["candidates"]
    )
    expected = (
        "technical_intended_exits",
        "technical_corrected_exits",
        "fixed_8",
        "fixed_10",
        "entry_atr14x3_1day",
    )
    if tuple(candidate.name for candidate in result) != expected:
        raise ExperimentInputError(
            "the comparison requires the five prespecified candidates"
        )
    if compare_entry_gate:
        result += (
            Candidate(
                "SEPARATE_entry_conflict_gate_fixed8",
                True,
                ExitPolicy(block_conflicting_entry=True),
            ),
            Candidate(
                "SEPARATE_completed_bar_general_fixed8",
                True,
                ExitPolicy(completed_bar_only_general=True),
            ),
        )
    return result


class EvaluationStrategy(TechnicalStrategy):
    """Pass prefix bars as warmup, then observe only the frozen evaluation interval."""

    def __init__(
        self,
        inner: TechnicalStrategy,
        risk: ExperimentRiskManager,
        split: EvaluationSplit,
        costs: BacktestCosts,
    ) -> None:
        super().__init__(inner.config)
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
        one_share_cost = self.costs.fee(decision.latest_price) + self.costs.fee(stop)
        one_share_cost += (decision.latest_price + stop) * self.costs.adverse_fraction
        return replace(
            decision, risk_per_share=decision.risk_per_share + one_share_cost
        )


def _write_rows(
    path: Path, rows: list[dict[str, str | int | float | bool | None | tuple[str, ...]]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def validate_daily_bars(bars: dict[str, list[Bar]]) -> None:
    for history in bars.values():
        dates = [bar.timestamp[:10] for bar in history]
        if len(set(dates)) != len(dates):
            raise ExperimentInputError(
                "1Day profiles require at most one bar per symbol per UTC date"
            )


def run_suite(
    settings: ExperimentSettings,
    bars: dict[str, list[Bar]],
    splits: tuple[EvaluationSplit, ...],
    output: Path,
    *,
    fx_rate: float,
    fx_history: tuple[FxPoint, ...] = (),
    operations_monthly_krw: float | None = None,
    compare_entry_gate: bool = False,
) -> None:
    if settings.dry_run is not True or settings.broker != "offline_csv":
        raise ExperimentInputError("offline dry_run profile required")
    validate_daily_bars(bars)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "protocol.json").exists():
        raise ExperimentInputError(
            "output protocol already exists; choose a fresh directory"
        )
    tables: dict[
        str, list[dict[str, str | int | float | bool | None | tuple[str, ...]]]
    ] = {
        name: []
        for name in (
            "summary",
            "monthly",
            "fills",
            "reasons",
            "equity",
            "entry_skips",
            "order_rejections",
        )
    }
    frozen = candidates(compare_entry_gate)
    protocol = {
        "settings": asdict(settings),
        "candidates": [asdict(value) for value in frozen],
        "splits": [asdict(value) for value in splits],
        "fx_rate": fx_rate,
        "operations_monthly_krw": operations_monthly_krw,
        "scope": "controlled TechnicalStrategy daily-close exits; no daily-minimum or learned-universe replay",
        "fill_model": "signal at close, next bar limit-touch/market-open fill; no intrabar stop ordering",
        "risk_model": "integer shares; per-share roundtrip cost upper bound using one-share minimum fees",
        "monthly_boundaries": "first/last observation months may be partial; USD target ratio is observed not future probability",
    }
    encoded = json.dumps(protocol, sort_keys=True).encode()
    protocol["protocol_sha256"] = hashlib.sha256(encoded).hexdigest()
    (output / "protocol.json").write_text(
        json.dumps(protocol, indent=2), encoding="utf-8"
    )
    for split in splits:
        split_fx = fx_at(split.start, fx_rate, fx_history)
        prefix = {
            symbol: [bar for bar in history if bar.timestamp <= split.end]
            for symbol, history in bars.items()
        }
        for candidate in frozen:
            for sizing in ("one_share", "risk_sized"):
                for risk_pct in (0.02, 0.04):
                    for scenario in settings.costs:
                        result, risk = _run_one(
                            settings,
                            prefix,
                            split,
                            candidate,
                            sizing,
                            risk_pct,
                            scenario,
                            split_fx,
                        )
                        observations = tuple(
                            point
                            for point in result.equity_curve
                            if point.timestamp >= split.start
                        )
                        evaluated = replace(result, equity_curve=observations)
                        performance = summarize(
                            evaluated,
                            fx_rate=split_fx,
                            operations_monthly_krw=operations_monthly_krw,
                            fx_history=fx_history,
                        )
                        key = {
                            "split": split.name,
                            "candidate": candidate.name,
                            "sizing": sizing,
                            "risk_budget_pct": risk_pct,
                            "cost_scenario": scenario.name,
                        }
                        tables["summary"].append(key | asdict(performance.summary))
                        for name, records in (
                            ("monthly", performance.months),
                            ("fills", result.trades),
                            ("reasons", performance.reasons),
                            ("equity", observations),
                            ("entry_skips", risk.skips),
                            ("order_rejections", result.rejections),
                        ):
                            tables[name].extend(
                                key | asdict(record) for record in records
                            )
    for name, rows in tables.items():
        _write_rows(output / f"{name}.csv", rows)


def _run_one(
    settings: ExperimentSettings,
    bars: dict[str, list[Bar]],
    split: EvaluationSplit,
    candidate: Candidate,
    sizing: Literal["one_share", "risk_sized"],
    risk_pct: float,
    scenario: CostScenario,
    fx_rate: float,
) -> tuple[BacktestResult, ExperimentRiskManager]:
    config = replace(settings.strategy, corrected_exits=candidate.corrected)
    inner = (
        TechnicalStrategy(config)
        if candidate.policy is None
        else ExperimentalExitStrategy(config, candidate.policy)
    )
    costs = BacktestCosts(
        scenario.commission_pct,
        scenario.minimum_commission,
        scenario.spread_bps,
        scenario.slippage_bps,
        1,
    )
    risk = ExperimentRiskManager(
        risk_pct=risk_pct,
        sizing=sizing,
        max_position_pct=settings.max_position_pct,
        cash_buffer_pct=settings.cash_buffer_pct,
        monthly_loss_stop_pct=settings.monthly_loss_stop_pct,
        costs=costs,
        max_total_position_pct=settings.max_total_position_pct,
    )
    strategy = EvaluationStrategy(inner, risk, split, costs)
    observer = inner if isinstance(inner, ExperimentalExitStrategy) else None
    tester = Backtester(
        strategy,
        risk,
        costs=costs,
        max_portfolio_risk_pct=settings.max_portfolio_risk_pct,
        max_trade_risk_pct=risk_pct,
        fill_observer=observer,
        risk_includes_costs=True,
    )
    return tester.run(bars, starting_cash=settings.starting_krw / fx_rate), risk
