from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, assert_never
from unittest.mock import patch

import pytest

from nasdaq_auto_trader.automatic_buy_receipts import automatic_buy_receipt_block
from nasdaq_auto_trader.brokers.alpaca import AlpacaClient, AlpacaCredentials
from nasdaq_auto_trader.models import OrderRequest, Position
from nasdaq_auto_trader.session_claims import AcceptedBuyReceipt, ClaimStatus, SignalKey
from tests.auto_symbol_live_guard_fixtures import _LiveMarketData
from tests.test_alpaca_order_history import history_row
from tests.test_automatic_pending_order_safety import make_engine


@pytest.mark.parametrize("outcome", ("filled", "canceled", "sold"))
def test_alpaca_notional_receipt_resolves_when_terminal_execution_is_reflected(
    tmp_path: Path, outcome: Literal["filled", "canceled", "sold"],
) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret", paper=False))
    engine = make_engine(tmp_path, client, _LiveMarketData())
    engine._clock = lambda: datetime(2026, 9, 9, 15, tzinfo=timezone.utc)
    store = engine.automatic_order_guard.session_store
    key = SignalKey("2026-09-09", "auto", "v1", "AAPL", "buy", "first")
    assert store.claim(key).granted
    store.complete(key, ClaimStatus.SUBMITTED, AcceptedBuyReceipt("receipt-1", "AAPL", "2026-09-09", 0))
    buy = {
        **history_row(), "qty": None, "notional": "100", "filled_qty": "0.5",
        "filled_avg_price": "200",
    }
    rows = [buy]
    positions = {"AAPL": Position("AAPL", 0.5, 100, 200)}
    match outcome:
        case "canceled":
            buy.update(status="canceled", filled_qty="0", filled_avg_price=None)
            positions = {}
        case "sold":
            rows.insert(0, {
                **buy, "id": "external-sell", "side": "sell",
                "submitted_at": "2026-09-09T14:30:00Z",
            })
            positions = {}
        case "filled":
            pass
        case unexpected:
            assert_never(unexpected)
    with patch.object(client, "_request", return_value=rows) as transport:
        blocked = automatic_buy_receipt_block(engine, OrderRequest("MSFT", "buy", notional=100), positions)
    assert blocked is None
    assert store.load_buy_receipts() == ()
    assert all(call.args[0] == "GET" for call in transport.call_args_list)


@pytest.mark.parametrize("status", ("partially_filled", "pending_cancel"))
def test_receipt_counts_confirmed_notional_sell_execution_while_sell_remains_active(
    tmp_path: Path, status: str,
) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret", paper=False))
    engine = make_engine(tmp_path, client, _LiveMarketData())
    engine._clock = lambda: datetime(2026, 9, 9, 15, tzinfo=timezone.utc)
    store = engine.automatic_order_guard.session_store
    key = SignalKey("2026-09-09", "auto", "v1", "AAPL", "buy", "first")
    assert store.claim(key).granted
    store.complete(key, ClaimStatus.SUBMITTED, AcceptedBuyReceipt("receipt-1", "AAPL", "2026-09-09", 0))
    rows = [{
        **history_row("external-sell"), "side": "sell", "status": status,
        "qty": None, "notional": "500", "filled_qty": "1",
        "submitted_at": "2026-09-09T14:30:00Z",
    }, history_row()]
    with patch.object(client, "_request", return_value=rows):
        blocked = automatic_buy_receipt_block(
            engine, OrderRequest("MSFT", "buy", notional=100),
            {"AAPL": Position("AAPL", 1, 123.45, 123.45)},
        )
    assert blocked is None
    assert store.load_buy_receipts() == ()


@pytest.mark.parametrize("status", ("partially_filled", "pending_cancel", ""))
def test_receipt_stays_pending_when_own_notional_buy_has_only_partial_execution(
    tmp_path: Path, status: str,
) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret", paper=False))
    engine = make_engine(tmp_path, client, _LiveMarketData())
    engine._clock = lambda: datetime(2026, 9, 9, 15, tzinfo=timezone.utc)
    store = engine.automatic_order_guard.session_store
    key = SignalKey("2026-09-09", "auto", "v1", "AAPL", "buy", "first")
    assert store.claim(key).granted
    store.complete(key, ClaimStatus.SUBMITTED, AcceptedBuyReceipt("receipt-1", "AAPL", "2026-09-09", 0))
    row = {
        **history_row(), "status": status, "qty": None, "notional": "500", "filled_qty": "1",
    }
    with patch.object(client, "_request", return_value=[row]):
        blocked = automatic_buy_receipt_block(
            engine, OrderRequest("MSFT", "buy", notional=100),
            {"AAPL": Position("AAPL", 1, 123.45, 123.45)},
        )
    assert blocked is not None
    assert len(store.load_buy_receipts()) == 1
