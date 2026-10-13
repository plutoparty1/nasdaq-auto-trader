"""Offline five-minute executions with prior-session daily technical indicators."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from math import isfinite
from pathlib import Path

from .backtest import Backtester
from .backtest_costs import BacktestCosts
from .backtest_types import BacktestResult
from .entry_comparison import JsonValue, _write_rows
from .entry_comparison_metrics import entry_outcome
from .entry_comparison_risk import MatchedEntryRisk
from .entry_policy_experiment import EntryPolicyStrategy
from .entry_policy_experiment_models import completed_timestamp, market_session
from .entry_pricing import price_entry_decision
from .exit_experiment import EvaluationSplit, validate_daily_bars
from .exit_experiment_config import CostScenario, ExperimentInputError
from .exit_experiment_metrics import FxPoint, summarize
from .models import Bar, Position, TradeDecision
from .strategy_config import StrategyConfig


def _timestamp(value: str) -> datetime:
    parsed = completed_timestamp(value)
    if parsed is None:
        raise ExperimentInputError("replay timestamps require an explicit timezone")
    return parsed


@dataclass(frozen=True, slots=True)
class ReplaySession:
    opens_at: str
    closes_at: str

    def __post_init__(self) -> None:
        if _timestamp(self.opens_at) >= _timestamp(self.closes_at):
            raise ExperimentInputError("replay session open must precede close")


def filter_completed_intraday(
    bars: dict[str, list[Bar]], sessions: tuple[ReplaySession, ...], *,
    observed_at: str, timestamp_semantics: str,
) -> dict[str, list[Bar]]:
    """Keep completed regular-session observations; never infer unknown labels."""
    if timestamp_semantics not in {"interval_end", "available_after_next_label"}:
        raise ExperimentInputError("require interval_end or available_after_next_label semantics")
    cutoff = _timestamp(observed_at)
    windows = [(_timestamp(item.opens_at), _timestamp(item.closes_at)) for item in sessions]
    result: dict[str, list[Bar]] = {}
    for symbol, history in bars.items():
        selected = []
        seen: set[datetime] = set()
        for bar in history:
            timestamp = _timestamp(bar.timestamp)
            if timestamp.second or timestamp.microsecond or timestamp.minute % 5:
                raise ExperimentInputError("intraday labels must align to a five-minute grid")
            if timestamp_semantics == "available_after_next_label":
                timestamp += timedelta(minutes=5)
            if timestamp in seen:
                raise ExperimentInputError("duplicate intraday timestamps")
            seen.add(timestamp)
            if timestamp > cutoff or not any(start < timestamp <= end for start, end in windows):
                continue
            selected.append(replace(bar, timestamp=timestamp.isoformat()))
        if selected:
            result[symbol] = sorted(selected, key=lambda bar: bar.timestamp)
    if not result:
        raise ExperimentInputError("no completed regular-session intraday bars")
    return result


class IntradayEvaluation:
    """Mutable adapter keeps risk clock aligned while reusing a daily signal snapshot."""

    def __init__(self, inner: EntryPolicyStrategy, risk: MatchedEntryRisk,
                 daily: dict[str, list[Bar]], costs: BacktestCosts) -> None:
        self.inner, self.risk, self.daily, self.costs = inner, risk, daily, costs
        self._snapshots: dict[tuple[str, str], list[Bar]] = {}

    def decide(self, symbol: str, bars: list[Bar], position: Position | None) -> TradeDecision:
        current = bars[-1]
        self.risk.timestamp = current.timestamp
        session = market_session(current.timestamp)
        key = (symbol, session)
        if key not in self._snapshots:
            self._snapshots[key] = sorted(
                (bar for bar in self.daily.get(symbol, [])
                 if market_session(bar.timestamp) < session
                 and _timestamp(bar.timestamp) < _timestamp(current.timestamp)),
                key=lambda bar: _timestamp(bar.timestamp),
            )
        history = self._snapshots[key]
        decision = self.inner.evaluate(
            symbol, history, position, evaluation_timestamp=current.timestamp,
            completed_bar_id=history[-1].timestamp if history else None,
        )
        decision = price_entry_decision(decision, current.close, self.inner.config.stop_loss_pct)
        if decision.action != "buy" or decision.risk_per_share is None:
            return decision
        stop = max(0, decision.latest_price - decision.risk_per_share)
        cost = self.costs.fee(decision.latest_price) + self.costs.fee(stop)
        cost += (decision.latest_price + stop) * self.costs.adverse_fraction
        return replace(decision, risk_per_share=decision.risk_per_share + cost)


def run_intraday_replay(
    config: StrategyConfig, daily: dict[str, list[Bar]], intraday: dict[str, list[Bar]],
    sessions: tuple[ReplaySession, ...], output: Path, costs: tuple[CostScenario, ...], *,
    fx_rate: float, manifest: dict[str, JsonValue], fx_history: tuple[FxPoint, ...] = (),
) -> None:
    """Freeze an A/B/C protocol before producing short-window simulation evidence."""
    if (output / "protocol.json").exists():
        raise ExperimentInputError("output already has a frozen protocol; choose a fresh directory")
    if output.exists() and any(output.iterdir()):
        raise ExperimentInputError("nonempty replay output is preserved; choose a fresh directory")
    if not isfinite(fx_rate) or fx_rate <= 0:
        raise ExperimentInputError("positive finite FX rate is required")
    validate_daily_bars(daily)
    semantics, observed = manifest.get("bar_timestamp_semantics"), manifest.get("collected_at")
    if not isinstance(semantics, str) or not isinstance(observed, str):
        raise ExperimentInputError("manifest requires timestamp semantics and collected_at")
    events = filter_completed_intraday(intraday, sessions, observed_at=observed,
                                       timestamp_semantics=semantics)
    stamps = sorted(bar.timestamp for history in events.values() for bar in history)
    split = EvaluationSplit("short_intraday_observation", stamps[0], stamps[-1])
    protocol = {"strategy": asdict(config), "policies": ["A", "B", "C"],
                "common_risk_pct": .01, "starting_krw": 80000, "quantity": 1,
                "indicator_timeframe": "1Day", "execution_timeframe": "5Min",
                "indicator_sampling": "strictly prior market-session completed daily bars",
                "sessions": [asdict(item) for item in sessions], "split": asdict(split),
                "costs": [asdict(item) for item in costs], "fx_rate": fx_rate,
                "fill_model": "next observed five-minute bar; DAY expires on that bar if untouched",
                "timestamp_semantics": semantics,
                "scope": "matched-risk proxy, not historical execution reconstruction",
                "monthly_extrapolation": False, "data_manifest": manifest}
    protocol["protocol_sha256"] = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    tables: dict[str, list[dict[str, JsonValue]]] = {name: [] for name in
        ("summary", "fills", "reasons", "equity", "entry_skips", "order_rejections", "decisions")}
    for policy in ("A", "B", "C"):
        for scenario in costs:
            cost = BacktestCosts(scenario.commission_pct, scenario.minimum_commission,
                                 scenario.spread_bps, scenario.slippage_bps, 1)
            strategy = EntryPolicyStrategy(config, policy)
            risk = MatchedEntryRisk(strategy, cost)
            adapter = IntradayEvaluation(strategy, risk, daily, cost)
            result = Backtester(adapter, risk, costs=cost, max_trade_risk_pct=.01,
                                max_total_position_pct=.5, fill_observer=strategy,
                                risk_includes_costs=True).run(
                                    events, starting_cash=80000 / fx_rate)
            performance = summarize(result, fx_rate=fx_rate, fx_history=fx_history,
                                    operations_monthly_krw=None)
            outcome = entry_outcome(result, strategy, performance, split)
            summary = performance.summary
            key = {"policy": policy, "cost_scenario": scenario.name}
            tables["summary"].append(key | asdict(outcome) | {
                "period_return_pct": result.return_pct,
                "period_krw_return_pct": summary.cumulative_krw_return_pct,
                "max_drawdown_pct": result.max_drawdown_pct,
                "completed_roundtrips": summary.completed_roundtrips,
                "average_holding_minutes": None if summary.average_holding_hours is None else summary.average_holding_hours * 60,
                "trading_cost_usd": summary.trading_cost_usd,
                "evidence_status": summary.evidence_status,
                "monthly_return_pct": None, "worst_month_pct": None,
                "five_minute_grid_general_exit_fills": _next_grid_general_exits(result, strategy),
            })
            for name, records in (("fills", result.trades), ("reasons", performance.reasons),
                                  ("equity", result.equity_curve), ("entry_skips", risk.skips),
                                  ("order_rejections", result.rejections), ("decisions", strategy.records)):
                tables[name].extend(key | asdict(record) for record in records)
    for name, rows in tables.items():
        _write_rows(output / f"{name}.csv", rows)


def _next_grid_general_exits(result: BacktestResult, strategy: EntryPolicyStrategy) -> int:
    protected = {"fixed_stop_loss", "atr_stop_loss", "fixed_take_profit", "atr_take_profit", "trailing_profit_protection"}
    count = 0
    for buy in (fill for fill in result.trades if fill.side == "buy"):
        following = next((record for record in strategy.records if record.symbol == buy.symbol
                          and record.evaluation_timestamp >= buy.timestamp), None)
        if following is None:
            continue
        count += any(fill.side == "sell" and fill.symbol == buy.symbol
                     and fill.signal_timestamp == following.evaluation_timestamp
                     and _timestamp(fill.timestamp) - _timestamp(buy.timestamp) == timedelta(minutes=5)
                     and not protected.intersection(fill.reasons) for fill in result.trades)
    return count
