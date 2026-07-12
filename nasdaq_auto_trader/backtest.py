"""Event-driven CSV backtesting with close-signal, next-open execution."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from math import isfinite, sqrt

from .models import AccountSnapshot, Bar, OrderRequest, Position, TradeDecision
from .risk import RiskManager
from .strategy import TechnicalStrategy


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


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """Portfolio value after one market timestamp."""

    timestamp: str
    equity: float
    cash: float
    positions_value: float


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Backtest summary, trade blotter, and equity curve."""

    starting_cash: float
    ending_value: float
    trades: tuple[BacktestTrade, ...] = ()
    equity_curve: tuple[EquityPoint, ...] = ()

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


class Backtester:
    """Apply the strategy and risk rules to historical bars in timestamp order."""

    def __init__(self, strategy: TechnicalStrategy, risk_manager: RiskManager) -> None:
        self.strategy = strategy
        self.risk_manager = risk_manager

    def run(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        starting_cash: float = 10_000,
    ) -> BacktestResult:
        """Run a close-signal, next-open execution simulation."""

        if not isfinite(starting_cash) or starting_cash <= 0:
            raise ValueError("starting_cash must be a finite number greater than zero")
        cash = starting_cash
        histories: dict[str, list[Bar]] = defaultdict(list)
        latest_prices: dict[str, float] = {}
        positions: dict[str, Position] = {}
        pending_orders: dict[str, tuple[OrderRequest, TradeDecision, str]] = {}
        trades: list[BacktestTrade] = []
        equity_curve: list[EquityPoint] = []

        events_by_timestamp: dict[str, list[Bar]] = defaultdict(list)
        for symbol, bars in bars_by_symbol.items():
            for bar in sorted(bars, key=lambda item: item.timestamp):
                events_by_timestamp[bar.timestamp].append(bar)

        for timestamp in sorted(events_by_timestamp):
            bars_at_timestamp = sorted(
                events_by_timestamp[timestamp],
                key=lambda item: item.symbol,
            )

            for bar in bars_at_timestamp:
                cash = self._execute_pending(
                    bar,
                    cash,
                    positions,
                    pending_orders,
                    trades,
                )
                histories[bar.symbol].append(bar)
                latest_prices[bar.symbol] = bar.close
                if bar.symbol in positions:
                    position = positions[bar.symbol]
                    positions[bar.symbol] = replace(
                        position,
                        market_value=position.qty * bar.close,
                    )

            account = self._account(cash, positions, latest_prices)
            for bar in bars_at_timestamp:
                position = positions.get(bar.symbol)
                decision = self.strategy.decide(
                    bar.symbol,
                    histories[bar.symbol],
                    position,
                )
                order = self.risk_manager.build_order(
                    decision,
                    account,
                    position,
                    decision.latest_price,
                )
                if order is not None:
                    pending_orders[bar.symbol] = (order, decision, timestamp)

            equity_curve.append(self._equity_point(timestamp, cash, positions, latest_prices))

        ending_value = self._account(cash, positions, latest_prices).equity
        return BacktestResult(starting_cash, ending_value, tuple(trades), tuple(equity_curve))

    def _execute_pending(
        self,
        bar: Bar,
        cash: float,
        positions: dict[str, Position],
        pending_orders: dict[str, tuple[OrderRequest, TradeDecision, str]],
        trades: list[BacktestTrade],
    ) -> float:
        """Execute yesterday's signal at today's opening price."""

        pending = pending_orders.pop(bar.symbol, None)
        if pending is None:
            return cash

        order, decision, signal_timestamp = pending
        execution_price = bar.open
        if execution_price <= 0:
            return cash

        if order.side == "buy" and order.notional is not None:
            notional = min(order.notional, cash)
            if notional <= 0:
                return cash
            qty = notional / execution_price
            positions[bar.symbol] = Position(
                symbol=bar.symbol,
                qty=qty,
                market_value=qty * bar.close,
                avg_entry_price=execution_price,
            )
            trades.append(
                BacktestTrade(
                    signal_timestamp,
                    bar.timestamp,
                    bar.symbol,
                    "buy",
                    execution_price,
                    qty,
                    notional,
                    tuple(decision.reasons),
                )
            )
            return cash - notional

        if order.side == "sell":
            position = positions.get(bar.symbol)
            if position is None:
                return cash
            qty = min(order.qty or position.qty, position.qty)
            notional = qty * execution_price
            pnl = qty * (execution_price - position.avg_entry_price)
            remaining_qty = position.qty - qty
            if remaining_qty <= 1e-12:
                positions.pop(bar.symbol, None)
            else:
                positions[bar.symbol] = Position(
                    bar.symbol,
                    remaining_qty,
                    remaining_qty * bar.close,
                    position.avg_entry_price,
                )
            trades.append(
                BacktestTrade(
                    signal_timestamp,
                    bar.timestamp,
                    bar.symbol,
                    "sell",
                    execution_price,
                    qty,
                    notional,
                    tuple(decision.reasons),
                    pnl,
                )
            )
            return cash + notional

        return cash

    def _account(
        self,
        cash: float,
        positions: dict[str, Position],
        latest_prices: dict[str, float],
    ) -> AccountSnapshot:
        """Build an account snapshot from current simulated state."""

        positions_value = self._positions_value(positions, latest_prices)
        equity = cash + positions_value
        return AccountSnapshot(cash=cash, equity=equity, buying_power=cash)

    def _equity_point(
        self,
        timestamp: str,
        cash: float,
        positions: dict[str, Position],
        latest_prices: dict[str, float],
    ) -> EquityPoint:
        """Capture one portfolio-equity observation."""

        positions_value = self._positions_value(positions, latest_prices)
        return EquityPoint(timestamp, cash + positions_value, cash, positions_value)

    def _positions_value(
        self,
        positions: dict[str, Position],
        latest_prices: dict[str, float],
    ) -> float:
        """Mark open positions to the latest seen close."""

        total = 0.0
        for symbol, position in positions.items():
            total += position.qty * latest_prices.get(symbol, position.avg_entry_price)
        return total
