from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.models import AccountSnapshot, Position
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.auto_symbol_live_guard_fixtures import (
    _LiveBroker, _LiveMarketData, _LiveSellMarketData, _bars, _live_engine, _write_champion,
)


@dataclass(frozen=True, slots=True)
class PendingOrder:
    symbol: str
    side: str


class PendingBroker(_LiveBroker):
    def __init__(self, pending=()):
        super().__init__("accepted")
        self.pending = pending
        self.history = ()

    def list_open_orders(self):
        return self.pending

    def list_order_history(self, start_date, end_date):
        return self.history

    def submit_order(self, order):
        response = super().submit_order(order)
        self.pending = (*self.pending, PendingOrder(order.symbol, order.side))
        return response


def make_engine(tmp_path, broker, market):
    paths = StrategyArtifactPaths.from_root(tmp_path / "artifacts")
    _write_champion(paths)
    guard = AutomaticOrderGuard(
        paths, TradingSessionStore(tmp_path / "session.json"), NullAuditLogger(),
    )
    engine = _live_engine(paths, guard, broker, market_data=market)
    engine.config = replace(engine.config, timeframe="1Min")
    return engine


def test_accepted_unfilled_buy_cannot_repeat_on_next_signal(tmp_path: Path):
    # Given a broker whose accepted order remains unfilled.
    broker = PendingBroker()
    market = _LiveMarketData()
    market.get_stock_bars = lambda symbols, *_args, **_kwargs: {
        symbol: [replace(bar, timestamp="2026-07-13T14:29:00+00:00") for bar in _bars(symbol)]
        for symbol in symbols
    }
    engine = make_engine(tmp_path, broker, market)
    engine.trading_settings = replace(engine.trading_settings, unattended_interval_minutes=5)
    engine.run_once()
    assert len(broker.orders) == 1
    engine._clock = lambda: datetime(2026, 7, 13, 14, 40, tzinfo=timezone.utc)
    market.get_stock_bars = lambda symbols, *_args, **_kwargs: {
        symbol: [replace(bar, timestamp="2026-07-13T14:39:00+00:00") for bar in _bars(symbol)]
        for symbol in symbols
    }

    # When the next interval produces a fresh signal with no filled positions.
    results = engine.run_once()

    # Then the pending buy is preserved as exposure and cannot be duplicated.
    assert len(broker.orders) == 1
    assert any("open_order" in item.get("response", {}).get("reason", "") for item in results)


def test_accepted_receipt_blocks_duplicate_while_broker_snapshots_lag(tmp_path: Path):
    # Given a successful submission not yet visible in broker queries.
    broker = PendingBroker()
    market = _LiveMarketData()
    market.get_stock_bars = lambda symbols, *_args, **_kwargs: {
        symbol: [replace(bar, timestamp="2026-07-13T14:29:00+00:00") for bar in _bars(symbol)]
        for symbol in symbols
    }
    engine = make_engine(tmp_path, broker, market)
    engine.trading_settings = replace(engine.trading_settings, unattended_interval_minutes=5)
    engine.run_once()
    broker.pending = ()
    engine._clock = lambda: datetime(2026, 7, 13, 14, 40, tzinfo=timezone.utc)
    market.get_stock_bars = lambda symbols, *_args, **_kwargs: {
        symbol: [replace(bar, timestamp="2026-07-13T14:39:00+00:00") for bar in _bars(symbol)]
        for symbol in symbols
    }
    # When a fresh signal arrives before broker history or positions catch up.
    engine.run_once()
    # Then the durable receipt prevents a second broker submission.
    assert len(broker.orders) == 1


@pytest.mark.parametrize("pending_side", ["buy", "sell"])
def test_same_symbol_pending_order_blocks_protective_sell(tmp_path: Path, pending_side: str):
    # Given an outstanding order for the position needing protection.
    broker = PendingBroker((PendingOrder("AAPL", pending_side),))
    engine = make_engine(tmp_path, broker, _LiveSellMarketData())
    # When a protective exit is evaluated.
    engine.run_once()
    # Then no overlapping sell is submitted.
    assert broker.orders == []


def test_unrelated_pending_buy_preserves_verified_protective_sell(tmp_path: Path):
    # Given a pending buy for another symbol and a verified held position.
    broker = PendingBroker((PendingOrder("MSFT", "buy"),))
    engine = make_engine(tmp_path, broker, _LiveSellMarketData())
    # When the held position triggers its stop.
    engine.run_once()
    # Then that distinct position can still be sold.
    assert [(order.symbol, order.side) for order in broker.orders] == [("AAPL", "sell")]


@pytest.mark.parametrize("condition", ["exposure", "cash", "missing_sell_position", "query_failure"])
def test_submit_rechecks_fresh_portfolio_and_open_orders(tmp_path: Path, condition: str):
    # Given portfolio data that changes after the strategy cycle reads it.
    broker = PendingBroker()
    market = _LiveSellMarketData() if condition == "missing_sell_position" else _LiveMarketData()
    if condition == "exposure":
        market.list_positions = lambda refresh=False: {
            "HELD": Position("HELD", 1, 10_000, 10_000)
        } if refresh else {}
    if condition == "cash":
        market.get_account = lambda refresh=False: Account