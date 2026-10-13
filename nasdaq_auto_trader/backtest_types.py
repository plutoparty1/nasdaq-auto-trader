from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Protocol

from .models import Position


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    """A simulated trade execution."""

    signal_timestamp: str
    timestamp: str
    symbol: str
    side: str
    price: float
    qty: float
    notional: float
    reasons: tuple[str, ...]
    pnl: float = 0.0
    fee: float = 0.0
    gross_pnl: float = 0.0
    allocated_entry_fee: float = 0.0
    execution_cost: float = 0.0


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """Portfolio value after one market timestamp."""

    timestamp: str
    equity: float
    cash: float
    positions_value: float


@dataclass(frozen=True, slots=True)
class BacktestRejection:
    signal_timestamp: str
    timestamp: str
    symbol: str
    reason: str


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Backtest summary, trade blotter, and equity curve."""

    starting_cash: float
    ending_value: float
    trades: tuple[BacktestTrade, ...] = ()
    equity_curve: tuple[EquityPoint, ...] = ()
    rejections: tuple[BacktestRejection, ...] = ()
    ending_positions: tuple[Position, ...] = ()

    @property
    def return_pct(self) -> float:
        """Return total percentage gain or loss."""

        if self.starting_cash == 0:
            return 0.0
        return (self.ending_value - self.starting_cash) / self.starting_cash * 100

    @property
    def max_drawdown_pct(self) -> float:
        """Return the largest peak-to-trough equity decline."""

        peak = self.starting_cash
        max_drawdown = 0.0
        for point in self.equity_curve:
            peak = max(peak, point.equity)
            if peak > 0:
                max_drawdown = min(max_drawdown, point.equity / peak - 1)
        return max_drawdown * 100

    @property
    def sharpe_ratio(self) -> float:
        """Return annualized Sharpe using daily risk-free rate of zero."""

        if len(self.equity_curve) < 2:
            return 0.0
        returns: list[float] = []
        previous = self.equity_curve[0].equity
        for point in self.equity_curve[1:]:
            if previous > 0:
                returns.append(point.equity / previous - 1)
            previous = point.equity
        if len(returns) < 2:
            return 0.0
        mean_return = sum(returns) / len(returns)
        variance = sum((value - mean_return) ** 2 for value in returns) / (
            len(returns) - 1
        )
        if variance == 0:
            return 0.0
        return mean_return / sqrt(variance) * sqrt(252)

    @property
    def trade_count(self) -> int:
        """Return the number of simulated executions."""

        return len(self.trades)

    @property
    def win_rate(self) -> float:
        """Return percentage of profitable closed trades."""

        closed = [trade for trade in self.trades if trade.side == "sell"]
        if not closed:
            return 0.0
        wins = sum(1 for trade in closed if trade.pnl > 0)
        return wins / len(closed) * 100


class BacktestFillObserver(Protocol):
    """Entry notifications contain updated average price and total held quantity."""

    def initial_stop_for(self, symbol: str, fill_price: float) -> float | None: ...

    def register_entry_fill(
        self, symbol: str, price: float, qty: float, timestamp: str
    ) -> None: ...

    def register_exit_fill(self, symbol: str, remaining_qty: float) -> None: ...
