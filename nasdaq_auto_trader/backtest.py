"""Event-driven CSV backtesting with close signals and subsequent-bar fills."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from math import isfinite
from typing import Protocol

from .backtest_costs import BacktestCosts
from .backtest_execution import ExecutionBook
from .backtest_types import (
    BacktestFillObserver,
    BacktestRejection,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)
from .models import AccountSnapshot, Bar, OrderRequest, Position, TradeDecision

__all__ = [
    "BacktestCosts",
    "BacktestFillObserver",
    "BacktestRejection",
    "BacktestResult",
    "BacktestTrade",
    "Backtester",
    "EquityPoint",
]


class BacktestStrategy(Protocol):
    def decide(
        self, symbol: str, bars: list[Bar], position: Position | None
    ) -> TradeDecision: ...


class BacktestRisk(Protocol):
    def build_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None: ...


class Backtester:
    """Offline simulator; daily OHLC does not reconstruct intrabar protective exits."""

    def __init__(
        self,
        strategy: BacktestStrategy,
        risk_manager: BacktestRisk,
        *,
        costs: BacktestCosts | None = None,
        max_portfolio_risk_pct: float | None = None,
        max_trade_risk_pct: float | None = None,
        fill_observer: BacktestFillObserver | None = None,
        risk_includes_costs: bool = False,
        max_total_position_pct: float | None = None,
        execution_book_type: type[ExecutionBook] = ExecutionBook,
        on_book_created: Callable[[ExecutionBook], None] | None = None,
    ) -> None:
        self.execution_book_type = execution_book_type
        self.on_book_created = on_book_created
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.costs = costs or BacktestCosts()
        for limit in (
            max_portfolio_risk_pct,
            max_trade_risk_pct,
            max_total_position_pct,
        ):
            if limit is not None and (not isfinite(limit) or not 0 < limit <= 1):
                raise ValueError("backtest risk limits must be fractions in (0, 1]")
        self.max_portfolio_risk_pct = max_portfolio_risk_pct
        self.max_trade_risk_pct = max_trade_risk_pct
        self.fill_observer = fill_observer
        self.risk_includes_costs = risk_includes_costs
        self.max_total_position_pct: float | None = max_total_position_pct

    def run(
        self, bars_by_symbol: dict[str, list[Bar]], starting_cash: float = 10_000
    ) -> BacktestResult:
        if not isfinite(starting_cash) or starting_cash <= 0:
            raise ValueError("starting_cash must be a finite number greater than zero")
        book = self.execution_book_type(
            starting_cash,
            self.costs,
            self.max_portfolio_risk_pct,
            self.max_trade_risk_pct,
            self.fill_observer,
            self.risk_includes_costs,
            max_total_position_pct=self.max_total_position_pct,
        )
        if self.on_book_created is not None:
            self.on_book_created(book)
        histories: dict[str, list[Bar]] = defaultdict(list)
        curve: list[EquityPoint] = []
        events: dict[str, list[Bar]] = defaultdict(list)
        for symbol, bars in bars_by_symbol.items():
            seen: set[str] = set()
            for bar in bars:
                if bar.symbol != symbol or not bar.timestamp or bar.timestamp in seen:
                    raise ValueError(
                        "bars must have matching symbols and unique nonempty timestamps"
                    )
                if not all(
                    isfinite(v) and v > 0
                    for v in (bar.open, bar.high, bar.low, bar.close)
                ):
                    raise ValueError("OHLC prices must be positive finite values")
                if bar.low > min(bar.open, bar.close) or bar.high < max(
                    bar.open, bar.close
                ):
                    raise ValueError("OHLC bounds are inconsistent")
                seen.add(bar.timestamp)
                events[bar.timestamp].append(bar)
        for timestamp in sorted(events):
            current = sorted(events[timestamp], key=lambda bar: bar.symbol)
            # Opening fills cannot use current-bar closing prices in risk equity.
            for bar in current:
                if bar.symbol in book.positions:
                    position = book.positions[bar.symbol]
                    book.positions[bar.symbol] = replace(
                        position, market_value=position.qty * bar.open
                    )
            for bar in current:
                book.execute(bar)
            for bar in current:
                histories[bar.symbol].append(bar)
                if bar.symbol in book.positions:
                    position = book.positions[bar.symbol]
                    book.positions[bar.symbol] = replace(
                        position,
                        market_value=position.qty * bar.close,
                        high_water_price=max(
                            position.high_water_price or position.avg_entry_price,
                            bar.close,
                        ),
                    )
            for bar in current:
                if bar.symbol in book.pending:
                    continue
                position = book.positions.get(bar.symbol)
                decision = self.strategy.decide(
                    bar.symbol, histories[bar.symbol], position
                )
                order = self.risk_manager.build_order(
                    decision,
                    book.account(available=True),
                    position,
                    decision.latest_price,
                )
                if order is not None:
                    book.submit(order, decision, timestamp)
            account = book.account()
            curve.append(
                EquityPoint(
                    timestamp, account.equity, book.cash, account.equity - book.cash
                )
            )
        for pending in book.pending.values():
            book.reject(pending, curve[-1].timestamp, "end_of_data_unfilled")
        return BacktestResult(
            starting_cash,
            book.account().equity,
            tuple(book.trades),
            tuple(curve),
            tuple(book.rejections),
            tuple(book.positions.values()),
        )
