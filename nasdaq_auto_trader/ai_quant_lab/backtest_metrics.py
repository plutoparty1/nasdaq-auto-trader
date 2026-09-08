from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Protocol

from nasdaq_auto_trader.quant_analytics import (
    geometric_cagr,
    max_drawdown,
    sharpe_ratio,
    simple_returns,
    sortino_ratio,
)


@dataclass(frozen=True, slots=True)
class MetricTiming:
    """One timezone-aware timestamp per equity mark and explicit sampling basis."""

    timestamps: tuple[datetime, ...]
    periods_per_year: float

    def valid_for(self, count: int) -> bool:
        return (
            count >= 2
            and len(self.timestamps) == count
            and isfinite(self.periods_per_year)
            and self.periods_per_year > 0
            and all(value.utcoffset() is not None for value in self.timestamps)
            and all(end > start for start, end in zip(self.timestamps, self.timestamps[1:]))
        )


class TradeRecord(Protocol):
    @property
    def symbol(self) -> str: ...

    @property
    def side(self) -> str: ...

    @property
    def cost(self) -> float: ...


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    expectancy: float
    turnover: float
    trade_count: float
    annualization_available: bool = False
    calmar: float = 0.0
    profit_factor_available: bool = False

    def to_mapping(self) -> Mapping[str, float]:
        return {
            "total_return": self.total_return,
            "cagr": self.cagr,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "turnover": self.turnover,
            "trade_count": self.trade_count,
            "annualization_available": float(self.annualization_available),
            "calmar": self.calmar,
            "profit_factor_available": float(self.profit_factor_available),
        }


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    return_rate: float
    profit_loss: float


def calculate_backtest_metrics(
    equity_curve: Sequence[float],
    trades: Sequence[TradeRecord],
    timing: MetricTiming | None = None,
) -> BacktestMetrics:
    """Missing/invalid timing leaves annualized metrics zero and flagged unavailable."""
    if not equity_curve or any(
        not isfinite(value) or value <= 0 for value in equity_curve
    ):
        return _empty_metrics()
    total_return = (
        (equity_curve[-1] / equity_curve[0]) - 1
        if len(equity_curve) > 1
        else 0.0
    )
    period_returns = simple_returns(equity_curve)
    drawdown = max_drawdown(equity_curve)
    cagr = sharpe = sortino = 0.0
    annualization_available = timing is not None and timing.valid_for(len(equity_curve))
    if timing is not None and annualization_available:
        elapsed_years = (timing.timestamps[-1] - timing.timestamps[0]).total_seconds() / (365.25 * 86400)
        cagr = geometric_cagr(equity_curve, elapsed_years)
        sharpe = sharpe_ratio(period_returns, timing.periods_per_year)
        sortino = sortino_ratio(period_returns, timing.periods_per_year)
    closed_trades = _closed_trades(trades)
    wins = tuple(item for item in closed_trades if item.profit_loss > 0)
    losses = tuple(item for item in closed_trades if item.profit_loss < 0)
    gross_profit = sum(item.profit_loss for item in wins)
    gross_loss = abs(sum(item.profit_loss for item in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
    average_equity = (
        sum(equity_curve) / len(equity_curve) if equity_curve else 0.0
    )
    turnover = (
        sum(trade.cost for trade in trades) / average_equity
        if average_equity > 0
        else 0.0
    )
    return BacktestMetrics(
        total_return=total_return,
        cagr=cagr,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=drawdown,
        win_rate=len(wins) / len(closed_trades) if closed_trades else 0.0,
        profit_factor=profit_factor,
        expectancy=(
            sum(item.return_rate for item in closed_trades) / len(closed_trades)
            if closed_trades
            else 0.0
        ),
        turnover=turnover,
        trade_count=float(len(closed_trades)),
        annualization_available=annualization_available,
        calmar=cagr / drawdown if annualization_available and drawdown > 0 else 0.0,
        profit_factor_available=gross_loss > 0,
    )


def _closed_trades(trades: Sequence[TradeRecord]) -> tuple[ClosedTrade, ...]:
    entries: dict[str, float] = {}
    closed: list[ClosedTrade] = []
    for trade in trades:
        if trade.side == "buy":
            entries[trade.symbol] = trade.cost
            continue
        entry_cost = entries.pop(trade.symbol, 0.0)
        if entry_cost > 0:
            profit_loss = trade.cost - entry_cost
            closed.append(ClosedTrade(profit_loss / entry_cost, profit_loss))
    return tuple(closed)


def _empty_metrics() -> BacktestMetrics:
    return BacktestMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
