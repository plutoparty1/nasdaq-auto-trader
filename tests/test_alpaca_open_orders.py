from __future__ import annotations

from unittest.mock import patch

import pytest

from nasdaq_auto_trader.ai_quant_lab.types import JsonValue
from nasdaq_auto_trader.brokers.alpaca import AlpacaClient, AlpacaCredentials
from nasdaq_auto_trader.brokers.common import BrokerRequestError


def test_alpaca_returns_quantity_and_notional_open_orders() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    payload = [
        {"symbol": "AAPL", "side": "buy", "qty": "2", "filled_qty": "1"},
        {"symbol": "MSFT", "side": "sell", "qty": "1", "filled_qty": "0"},
        {"symbol": "NVDA", "side": "buy", "notional": "50", "qty": None},
    ]
    with patch.object(client, "_request", return_value=payload) as transport:
        orders = client.list_open_orders()

    assert [(order.symbol, order.side) for order in orders] == [
        ("AAPL", "buy"), ("MSFT", "sell"), ("NVDA", "buy")
    ]
    transport.assert_called_once_with(
        "GET", client.trading_base_url, "/v2/orders",
        {"status": "open", "limit": 500, "nested": "false"},
    )


@pytest.mark.parametrize(
    "payload",
    (
        {},
        [None],
        [{"symbol": "", "side": "buy", "qty": "1"}],
        [{"symbol": "AAPL ", "side": "buy", "qty": "1"}],
        [{"symbol": "AAPL", "side": "hold", "qty": "1"}],
        [{"symbol": "AAPL", "side": "buy", "qty": "NaN"}],
        [{"symbol": "AAPL", "side": "buy", "qty": "inf"}],
        [{"symbol": "AAPL", "side": "buy", "qty": "0"}],
        [{"symbol": "AAPL", "side": "buy", "qty": True}],
        [{"symbol": "AAPL", "side": "buy", "qty": "2", "filled_qty": "3"}],
        [{"symbol": "AAPL", "side": "buy", "qty": "2", "filled_qty": "NaN"}],
        [{"symbol": "AAPL", "side": "buy", "notional": "NaN"}],
        [{"symbol": "AAPL", "side": "buy"}],
        [{"symbol": "AAPL", "side": "buy", "qty": "1"}] * 500,
    ),
)
def test_alpaca_rejects_invalid_or_potentially_truncated_open_orders(
    payload: JsonValue,
) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    with patch.object(client, "_request", return_value=payload):
        with pytest.raises(BrokerRequestError):
            client.list_open_orders()


def test_alpaca_accepts_empty_open_order_response() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    with patch.object(client, "_request", return_value=[]):
        assert client.list_open_orders() == ()


@pytest.mark.parametrize("market_date,offset", (("2026-09-09", "-04:00"), ("2026-01-09", "-05:00")))
def test_alpaca_history_returns_exact_fill_evidence_with_new_york_date_bounds(
    market_date: str, offset: str,
) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {
        "id": "receipt-1", "symbol": "AAPL", "side": "buy",
        "qty": "2", "filled_qty": "2", "filled_avg_price": "123.45",
    }
    with patch.object(client, "_request", return_value=[row]) as transport:
        history = client.list_order_history(market_date, market_date)

    assert len(history) == 1
    assert (
        history[0].order_id, history[0].symbol, history[0].side,
        history[0].quantity, history[0].filled_quantity, history[0].average_fill_price,
    ) == ("receipt-1", "AAPL", "buy", 2.0, 2.0, 123.45)
    transport.assert_called_once_with(
        "GET", client.trading_base_url, "/v2/orders",
        {
            "status": "all", "limit": 500, "nested": "false",
            "after": f"{market_date[:-2]}08T23:59:59.999999{offset}",
            "until": f"{market_date[:-2]}10T00:00:00{offset}",
        },
    )


def test_alpaca_history_does_not_fabricate_quantity_for_notional_record() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {
        "id": "receipt-1", "symbol": "AAPL", "side": "buy",
        "qty": None, "notional": "50", "filled_qty": "0",
    }
    with patch.object(client, "_request", return_value=[row]):
        assert client.list_order_history("2026-09-09", "2026-09-09") == ()


@pytest.mark.parametrize("field,value", (("filled_qty", "NaN"), ("filled_qty", "3"), ("filled_avg_price", "inf"), ("id", "")))
def test_alpaca_history_rejects_invalid_fill_evidence(field: str, value: str) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {
        "id": "receipt-1", "symbol": "AAPL", "side": "buy",
        "qty": "2", "filled_qty": "2", "filled_avg_price": "123.45",
        field: value,
    }
    with patch.object(client, "_request", return_value=[row]):
        with pytest.raises(BrokerRequestError):
            client.list_order_history("2026-09-09", "2026-09-09")
