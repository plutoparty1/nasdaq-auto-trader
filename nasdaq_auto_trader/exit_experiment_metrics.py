"""Account equity metrics, including open positions and explicit FX assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median

from .backtest import BacktestResult


@dataclass(frozen=True, slots=True)
class FxPoint:
    timestamp: str
    usdkrw: float


@dataclass(frozen=True, slots=True)
class MonthlyPerformance:
    month: str
    ending_equity_usd: float
    ending_equity_krw: float
    usd_return_pct: float
    krw_return_pct: float
    fx_only_return_pct: float
    operations_cost_krw: float | None
    after_operations_equity_krw: float | None
    observation_start: str
    observation_end: str


@dataclass(frozen=True, slots=True)
class ReasonPerformance:
    reason: str
    sell_fills: int
    net_pnl_usd: float


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    evidence_status: str
    cumulative_return_pct: float
    cumulative_krw_return_pct: float
    median_monthly_return_pct: float
    target_months: int
    evaluated_months: int
    loss_month_ratio: float
    worst_month_pct: float
    max_drawdown_pct: float
    max_krw_drawdown_pct: float
    completed_roundtrips: int
    average_holding_hours: float | None
    win_rate_pct: float | None
    average_profit_usd: float | None
    average_loss_usd: float | None
    payoff_ratio: float | None
    commissions_usd: float
    execution_cost_usd: float
    trading_cost_usd: float
    operations_cost_krw: float | None
    after_operations_return_pct: float | None
    fx_mode: str
    final_open_positions_value_usd: float


@dataclass(frozen=True, slots=True)
class Performance:
    summary: PerformanceSummary
    months: tuple[MonthlyPerformance, ...]
    reasons: tuple[ReasonPerformance, ...]


def fx_at(timestamp: str, default: float, history: tuple[FxPoint, ...]) -> float:
    applicable = [point.usdkrw for point in history if point.timestamp <= timestamp]
    return applicable[-1] if applicable else default


def _closed_trades(
    result: BacktestResult,
) -> tuple[list[float], list[float], tuple[ReasonPerformance, ...]]:
    quantities: dict[str, float] = {}
    starts: dict[str, str] = {}
    net: dict[str, float] = {}
    profits: list[float] = []
    hours: list[float] = []
    reason_values: dict[str, list[float]] = {}
    known = {
        "fixed_stop_loss",
        "atr_stop_loss",
        "fixed_take_profit",
        "atr_take_profit",
        "trailing_profit_protection",
        "time_based_sell",
        "market_close",
    }
    for trade in result.trades:
        if trade.side == "buy":
            if quantities.get(trade.symbol, 0) <= 1e-10:
                starts[trade.symbol] = trade.timestamp
                net[trade.symbol] = 0.0
            quantities[trade.symbol] = quantities.get(trade.symbol, 0) + trade.qty
            continue
        quantities[trade.symbol] = quantities.get(trade.symbol, 0) - trade.qty
        net[trade.symbol] = net.get(trade.symbol, 0) + trade.pnl
        reason = next(
            (value for value in trade.reasons if value in known),
            "technical_sell_signal",
        )
        reason_values.setdefault(reason, []).append(trade.pnl)
        if quantities[trade.symbol] <= 1e-10:
            profits.append(net[trade.symbol])
            elapsed = datetime.fromisoformat(trade.timestamp) - datetime.fromisoformat(
                starts[trade.symbol]
            )
            hours.append(elapsed.total_seconds() / 3600)
    reasons = tuple(
        ReasonPerformance(reason, len(values), sum(values))
        for reason, values in sorted(reason_values.items())
    )
    return profits, hours, reasons


def summarize(
    result: BacktestResult,
    *,
    fx_rate: float,
    operations_monthly_krw: float | None,
    fx_history: tuple[FxPoint, ...] = (),
) -> Performance:
    month_ends = {}
    month_starts: dict[str, str] = {}
    peak_krw = result.starting_cash * fx_rate
    max_krw_dd = 0.0
    for point in result.equity_curve:
        month = point.timestamp[:7]
        month_ends[month] = point
        month_starts.setdefault(month, point.timestamp)
        equity_krw = point.equity * fx_at(point.timestamp, fx_rate, fx_history)
        peak_krw = max(peak_krw, equity_krw)
        max_krw_dd = min(max_krw_dd, equity_krw / peak_krw - 1)
    previous_usd, previous_krw, previous_fx = (
        result.starting_cash,
        result.starting_cash * fx_rate,
        fx_rate,
    )
    months: list[MonthlyPerformance] = []
    for number, (month, point) in enumerate(sorted(month_ends.items()), 1):
        rate = fx_at(point.timestamp, fx_rate, fx_history)
        value_krw = point.equity * rate
        ops_total = (
            None if operations_monthly_krw is None else number * operations_monthly_krw
        )
        months.append(
            MonthlyPerformance(
                month,
                point.equity,
                value_krw,
                (point.equity / previous_usd - 1) * 100,
                (value_krw / previous_krw - 1) * 100,
                (rate / previous_fx - 1) * 100,
                operations_monthly_krw,
                None if ops_total is None else value_krw - ops_total,
                month_starts[month],
                point.timestamp,
            )
        )
        previous_usd, previous_krw, previous_fx = point.equity, value_krw, rate
    closed, hours, reasons = _closed_trades(result)
    wins = [value for value in closed if value > 0]
    losses = [value for value in closed if value < 0]
    average_win, average_loss = (
        (mean(wins) if wins else None),
        (mean(losses) if losses else None),
    )
    fees = sum(trade.fee for trade in result.trades)
    execution_cost = sum(trade.execution_cost for trade in result.trades)
    ops = (
        None if operations_monthly_krw is None else operations_monthly_krw * len(months)
    )
    end_krw = months[-1].ending_equity_krw if months else result.starting_cash * fx_rate
    after_ops = (
        None
        if ops is None
        else ((end_krw - ops) / (result.starting_cash * fx_rate) - 1) * 100
    )
    summary = PerformanceSummary(
        "no_executions" if not result.trades else "observed_sample_not_probability",
        result.return_pct,
        (end_krw / (result.starting_cash * fx_rate) - 1) * 100,
        median([month.usd_return_pct for month in months]) if months else 0.0,
        sum(month.usd_return_pct >= 10 - 1e-9 for month in months),
        len(months),
        sum(month.usd_return_pct < 0 for month in months) / len(months)
        if months
        else 0.0,
        min((month.usd_return_pct for month in months), default=0.0),
        result.max_drawdown_pct,
        max_krw_dd * 100,
        len(closed),
        mean(hours) if hours else None,
        100 * len(wins) / len(closed) if closed else None,
        average_win,
        average_loss,
        average_win / abs(average_loss)
        if average_win is not None and average_loss is not None
        else None,
        fees,
        execution_cost,
        fees + execution_cost,
        ops,
        after_ops,
        "historical_fx"
        if fx_history
        else "constant_fx_translation_not_actual_krw_return",
        result.equity_curve[-1].positions_value if result.equity_curve else 0.0,
    )
    return Performance(summary, tuple(months), reasons)
