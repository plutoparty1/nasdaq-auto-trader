from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nasdaq_auto_trader.automatic_buy_receipts import automatic_buy_receipt_block
from nasdaq_auto_trader.automatic_order_pending import (
    PendingOrderCheck,
    automatic_pending_order_block,
)
from nasdaq_auto_trader.models import OrderRequest, Position
from nasdaq_auto_trader.session_claims import AcceptedBuyReceipt, ClaimStatus, SignalKey
from tests.auto_symbol_live_guard_fixtures import _bars, _LiveMarketData
from tests.test_automatic_pending_order_safety import PendingBroker, make_engine


@dataclass(frozen=True, slots=True)
class History:
    order_id: str
    symbol: str
    side: str = "buy"
    quantity: float = 2
    filled_quantity: float = 0
    average_fill_price: float = 239
    status: str = "unknown"


def submitted_engine(tmp_path: Path):
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
    broker.pending = ()
    engine._clock = lambda: datetime(2026, 7, 13, 14, 40, tzinfo=timezone.utc)
    market.get_stock_bars = lambda symbols, *_args, **_kwargs: {
        symbol: [replace(bar, timestamp="2026-07-13T14:39:00+00:00") for bar in _bars(symbol)]
        for symbol in symbols
    }
    return engine, broker, market


@pytest.mark.parametrize("case", ["missing", "wrong_id", "partial", "portfolio_lag"])
def test_unresolved_receipt_blocks_buy_when_history_or_portfolio_lags(tmp_path, case):
    engine, broker, _market = submitted_engine(tmp_path)
    symbol = broker.orders[0].symbol
    if case != "missing":
        broker.history = (History(
            "foreign" if case == "wrong_id" else "1", symbol,
            filled_quantity=1 if case == "partial" else 2,
        ),)

    engine.run_once()

    assert len(broker.orders) == 1


@pytest.mark.parametrize("status", ["canceled", "rejected", "expired"])
def test_terminal_zero_fill_receipt_allows_next_signal(tmp_path, status):
    engine, broker, _market = submitted_engine(tmp_path)
    broker.history = (History("1", broker.orders[0].symbol, status=status),)

    engine.run_once()

    assert len(broker.orders) == 2


@pytest.mark.parametrize("status,filled", [("filled", 2), ("canceled", 1)])
def test_exact_fill_and_fresh_position_release_receipt_for_other_buy(tmp_path, status, filled):
    engine, broker, market = submitted_engine(tmp_path)
    symbol = broker.orders[0].symbol
    broker.history = (History("1", symbol, filled_quantity=filled, status=status),)
    market.list_positions = lambda refresh=False: {
        symbol: Position(symbol, filled, 239 * filled, 239),
    }

    engine.run_once()

    assert len(broker.orders) == 2
    assert broker.orders[1].symbol != symbol


def test_receipt_survives_engine_restart_while_history_is_missing(tmp_path):
    engine, broker, market = submitted_engine(tmp_path)
    restarted = make_engine(tmp_path, broker, market)
    restarted.trading_settings = engine.trading_settings
    restarted._clock = engine._clock

    restarted.run_once()

    assert len(broker.orders) == 1


@pytest.mark.parametrize("visible_qty", [2, 4])
def test_additional_buy_requires_previous_holdings_plus_new_fill(tmp_path, visible_qty):
    broker = PendingBroker()
    market = _LiveMarketData()
    market.list_positions = lambda refresh=False: {
        "AAPL": Position("AAPL", 2, 200, 100),
    }
    engine = make_engine(tmp_path, broker, market)
    engine.trading_settings = replace(engine.trading_settings, allow_additional_buy=True)
    order = OrderRequest("AAPL", "buy", qty=2, limit_price=100)
    checked = automatic_pending_order_block(engine, order, 100)
    assert isinstance(checked, PendingOrderCheck)
    assert checked.initial_position_qty == 2
    key = SignalKey("2026-07-13", "auto", "v1", "AAPL", "buy", "first")
    store = engine.automatic_order_guard.session_store
    assert store.claim(key).granted
    store.complete(key, ClaimStatus.SUBMITTED, AcceptedBuyReceipt(
        "1", "AAPL", "2026-07-13", checked.initial_position_qty,
    ))
    broker.h