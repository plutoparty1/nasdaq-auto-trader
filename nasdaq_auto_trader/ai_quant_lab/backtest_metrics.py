from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Protocol


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
        }


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    return_rate: float
    profit_loss: float


def calculate_backtest_metrics(
    equity_curve: Sequence[float],
    trades: Sequence[TradeRecord],
) -> BacktestMetrics:
    if not equity_curve or any(
        not isfinite(value) or value <= 0 for value in equity_curve
    ):
        return _empty_metrics()
    total_return = (
        (equity_curve[-1] / equity_curve[0]) - 1
        if len(equity_curve) > 1
        else 0.0
    )
    drawdown = _max_drawdown(equity_curve)
    period_returns = tuple(
        (equity_curve[index] / equity_curve[index - 1]) - 1
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1] > 0
    )
    average_return = (
        sum(period_returns) / len(period_returns) if period_returns else 0.0
    )
    variance = (
        sum((value - average_return) ** 2 for value in period_returns)
        / len(period_returns)
        if period_returns
        else 0.0
    )
    sharpe = average_return / (variance**0.5) if variance > 0 else 0.0
    closed_trades = _closed_trades(trades)
    wins = tuple(item for item in closed_trades if item.profit_loss > 0)
    losses = tuple(item for item in closed_trades if item.profit_loss < 0)
    gross_profit = sum(item.profit_loss for item in wins)
    gross_loss = abs(sum(item.profit_loss for item in losses))
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else 10.0 if gross_profit > 0 else 0.0
    )
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
        cagr=total_return,
        sharpe=sharpe,
        sortino=sharpe,
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


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value / peak) - 1)
    return abs(max_drawdown)
