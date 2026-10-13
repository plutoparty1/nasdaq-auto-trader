from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nasdaq_auto_trader.automatic_buy_receipts import automatic_buy_receipt_block
from nasdaq_auto_trader.automatic_order_pending import (
    PendingOrderCheck,
    automatic_pending_order_block,
)
from nasdaq_auto_trader.models import OrderRequest, Position
from tests.test_automatic_buy_receipts import History, submitted_engine


@dataclass(frozen=True, slots=True)
class TimedHistory(History):
    submitted_at: datetime | None = None
    is_original_order: bool = True
    requested_quantity_known: bool = True


BUY_TIME = datetime(2026, 7, 13, 14, 35, tzinfo=timezone.utc)


@pytest.mark.parametrize("sold", [1, 2])
def test_later_external_sale_reconciles_reduced_or_closed_position(
    tmp_path: Path, sold: int,
) -> None:
    # Given an exact full fill followed by an independently executed sale.
    engine, broker, _market = submitted_engine(tmp_path)
    symbol = broker.orders[0].symbol
    broker.history = (
        TimedHistory("1", symbol, filled_quantity=2, submitted_at=BUY_TIME),
        TimedHistory("external", symbol, side="sell", quantity=sold,
                     filled_quantity=sold, submitted_at=BUY_TIME + timedelta(minutes=1)),
    )
    remaining = 2 - sold
    positions = {symbol: Position(symbol, remaining, remaining * 239, 239)} if remaining else {}
    # When the next buy reconciles history with the current holdings.
    result = automatic_buy_receipt_block(engine, OrderRequest("MSFT", "buy", qty=1), positions)
    # Then settled exposure no longer blocks trading.
    assert result is None
    assert engine.automatic_order_guard.session_store.load_buy_receipts() == ()


def test_terminal_buy_does_not_block_verified_remaining_protective_sell(tmp_path: Path) -> None:
    # Given full execution and a smaller fresh holding after an external sale.
    engine, broker, market = submitted_engine(tmp_path)
    symbol = broker.orders[0].symbol
    broker.history = (History("1", symbol, filled_quantity=2),)
    market.list_positions = lambda refresh=False: {symbol: Position(symbol, 1, 239, 239)}
    # When protection sells the verified remaining share.
    result = automatic_pending_order_block(engine, OrderRequest(symbol, "sell", qty=1), 239)
    # Then the exit is allowed but unresolved buy exposure remains durable.
    assert isinstance(result, PendingOrderCheck)
    assert len(engine.automatic_order_guard.session_store.load_buy_receipts()) == 1


def test_fractional_external_sales_reconcile_exactly(tmp_path: Path) -> None:
    engine, broker, _market = submitted_engine(tmp_path)
    symbol = broker.orders[0].symbol
    broker.history = (
        TimedHistory("1", symbol, quantity=0.3, filled_quantity=0.3, submitted_at=BUY_TIME),
        TimedHistory("sale1", symbol, side="sell", quantity=0.1, filled_quantity=0.1,
                     submitted_at=BUY_TIME + timedelta(minutes=1)),
        TimedHistory("sale2", symbol, side="sell", quantity=0.2, filled_quantity=0.2,
                     submitted_at=BUY_TIME + timedelta(minutes=2)),
    )

    result = automatic_buy_receipt_block(engine, OrderRequest("MSFT", "buy", qty=1), {})

    assert result is None
    assert engine.automatic_order_guard.session_store.load_buy_receipts() == ()


def test_partial_notional_buy_is_not_mistaken_for_full_execution(tmp_path: Path) -> None:
    engine, broker, _market = submitted_engine(tmp_path)
    symbol = broker.orders[0].symbol
    broker.history = (
        TimedHistory("1", symbol, quantity=1, filled_quantity=1, status="partially_filled",
                     submitted_at=BUY_TIME, requested_quantity_known=False),
    )
    positions = {symbol: Position(symbol, 1, 239, 239)}

    result = automatic_buy_receipt_block(engine, OrderRequest("MSFT", "buy", qty=1), positions)

    assert result is not None
    assert engine.automatic_order_guard.session_store.load_buy_receipts()


def test_later_day_sale_is_queried_after_restart(tmp_path: Path) -> None:
    # Given a persisted buy and a sale executed the next market day.
    engine, broker, _market = submitted_engine(tmp_path)
    symbol = broker.orders[0].symbol
    buy = TimedHistory("1", symbol, filled_quantity=2, submitted_at=BUY_TIME)
    sell = TimedHistory("external", symbol, side="sell", filled_quantity=2,
                        submitted_at=BUY_TIME + timedelta(days=1))
    engine._clock = lambda: BUY_TIME + timedelta(days=1, minutes=5)

    def history(start_date: str, end_date: str) -> tuple[TimedHistory, ...]:
        return (buy, sell) if end_date >= "20260714" else (buy,)

    broker.list_order_history = history
    # When reconciliation reads the reopened persistent store on the later day.
    store = engine.automatic_order_guard.session_store
    engine.automatic_order_guard.session_store = type(store)(store.path)
    result = automatic_buy_receipt_block(engine, OrderRequest("MSFT", "buy", qty=1), {})
    # Then the next-day sale closes the receipt.
    assert result is None
    assert engine.automatic_order_guard.session_store.load_buy_receipts() == ()


@pytest.mark.parametrize("case", [
    "earlier", "same_time", "other_symbol", "missing_time", "naive_time", "duplicate",
    "oversold", "later_buy", "cancel_request",
])
def test_ambiguous_or_unrelated_sales_cannot_release_lagging_buy(
    tmp_path: Path, case: str,
) -> None:
    # Given a filled buy whose portfolio is still missing and unsuitable sale evidence.
    engine, broker, _market = submitted_engine(tmp_path)
    symbol = broker.orders[0].symbol
    buy = TimedHistory("1", symbol, filled_quantity=2, submitted_at=BUY_TIME)
    sell = TimedHistory("external", symbol, side="sell", filled_quantity=2,
                        submitted_at=BUY_TIME + timedelta(minutes=1))
    history = [buy, sell]
    if case == "earlier":
        history[1] = replace(sell, submitted_at=BUY_TIME - timedelta(minutes=1))
    elif case == "same_time":
        history[1] = replace(sell, submitted_at=BUY_TIME)
    elif case == "other_symbol":
        history[1] = replace(sell, symbol="OTHER")
    elif case == "missing_time":
        history[1] = replace(sell, submitted_at=None)
    elif case == "naive_time":
        history[1] = replace(sell, submitted_at=BUY_TIME.replace(tzinfo=None))
    elif case == "duplicate":
        history.append(sell)
    elif case == "oversold":
        history[1] = replace(sell, quantity=3, filled_quantity=3)
    elif case == "later_buy":
        history.append(TimedHistory("later", symbol, quantity=1, filled_quantity=1,
                                    submitted_at=BUY_TIME + timedelta(seconds=30)))
    elif case == "cancel_request":
        history[1] = replace(sell, is_original_order=False)
    broker.history = tuple(history)
    # When a new buy is checked against the lagging empty portfolio.
    result = automatic_buy_receipt_block(engine, OrderRequest("MSFT", "buy", qty=1), {})
    # Then no unexplained exposure disappears.
    assert result is not None
    assert result.reason == "automatic_buy_receipt_reconciliation_pending"
    assert len(engine.automatic_order_guard.session_store.load_buy_receipts()) == 1
