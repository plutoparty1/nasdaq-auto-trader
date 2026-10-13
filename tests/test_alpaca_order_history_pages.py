from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

from nasdaq_auto_trader.ai_quant_lab.types import JsonValue
from nasdaq_auto_trader.brokers.alpaca import AlpacaClient, AlpacaCredentials
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from tests.test_alpaca_order_history import history_row


def test_history_preserves_optional_timestamp_when_small_response_omits_it() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = history_row()
    del row["submitted_at"]
    with patch.object(client, "_request", return_value=[row]):
        history = client.list_order_history("20260909", "20260909")
    assert history[0].submitted_at is None


@pytest.mark.parametrize("value", (None, "2026-09-09T14:30:00Z", "2026-09-10T04:00:00Z"))
def test_history_rejects_cursor_row_when_date_or_ordering_is_unverifiable(value: JsonValue) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    first = [history_row(f"order-{index}") for index in range(500)]
    last = {**history_row("last"), "submitted_at": value}
    with patch.object(client, "_request", side_effect=[first, [last]]), pytest.raises(BrokerRequestError):
        client.list_order_history("20260909", "20260909")


def test_history_rejects_full_page_when_submission_timestamp_is_missing() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    rows = [{**history_row(f"order-{index}"), "submitted_at": None} for index in range(500)]
    with patch.object(client, "_request", return_value=rows), pytest.raises(BrokerRequestError):
        client.list_order_history("20260909", "20260909")


def test_history_rejects_invalid_notional_when_quantityless_row_would_be_omitted() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {**history_row(), "qty": None, "notional": "NaN"}
    with patch.object(client, "_request", return_value=[row]), pytest.raises(BrokerRequestError):
        client.list_order_history("20260909", "20260909")


def test_history_rejects_duplicates_when_quantityless_rows_would_be_omitted() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {**history_row(), "qty": None, "notional": "100"}
    with patch.object(client, "_request", return_value=[row, row]), pytest.raises(BrokerRequestError):
        client.list_order_history("20260909", "20260909")


def test_history_reads_final_empty_page_when_last_page_has_exactly_500_rows() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    rows = [history_row(f"order-{index}") for index in range(500)]
    with patch.object(client, "_request", side_effect=[rows, []]) as transport:
        history = client.list_order_history("20260909", "20260909")
    assert len(history) == 500
    assert transport.call_count == 2


def test_history_serializes_read_only_requests_when_using_real_transport() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret", paper=False))
    rows = [history_row(f"order-{index}") for index in range(500)]
    responses = [BytesIO(json.dumps(page).encode()) for page in (rows, [history_row("last")])]
    with patch("nasdaq_auto_trader.brokers.alpaca.urlopen", side_effect=responses) as connection:
        history = client.list_order_history("20260909", "20260909")
    assert len(history) == 501
    for call in connection.call_args_list:
        request = call.args[0]
        assert request.get_method() == "GET"
        assert request.data is None
        assert urlparse(request.full_url).netloc == "api.alpaca.markets"
    query = parse_qs(urlparse(connection.call_args_list[1].args[0].full_url).query)
    assert query == {"status": ["all"], "limit": ["500"], "nested": ["false"], "before_order_id": ["order-499"]}


@pytest.mark.parametrize("side,status,filled,price", (
    ("buy", "filled", "0.5", "200"), ("sell", "filled", "0.5", "200"),
    ("buy", "canceled", "0", None), ("buy", "expired", "0", None),
    ("buy", "rejected", "0", None), ("buy", "canceled", "0.25", "200"),
))
def test_history_retains_final_executed_shares_when_terminal_order_is_notional(
    side: str, status: str, filled: str, price: str | None,
) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {
        **history_row(), "side": side, "status": status, "qty": None, "notional": "100",
        "filled_qty": filled, "filled_avg_price": price,
    }
    with patch.object(client, "_request", return_value=[row]):
        history = client.list_order_history("20260909", "20260909")
    assert len(history) == 1
    assert (history[0].order_id, history[0].side, history[0].status) == ("receipt-1", side, status)
    assert history[0].quantity == history[0].filled_quantity == float(filled)
    assert history[0].requested_quantity_known is False


@pytest.mark.parametrize("status", ("new", "partially_filled", "pending_cancel", ""))
def test_history_retains_partial_notional_execution_when_requested_shares_remain_unknown(status: str) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {
        **history_row(), "status": status, "qty": None, "notional": "500",
        "filled_qty": "1",
    }
    with patch.object(client, "_request", return_value=[row]):
        history = client.list_order_history("20260909", "20260909")
    assert len(history) == 1
    assert history[0].quantity == history[0].filled_quantity == 1
    assert history[0].requested_quantity_known is False
    assert history[0].status == status


def test_history_preserves_known_requested_quantity_when_order_has_share_quantity() -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    with patch.object(client, "_request", return_value=[history_row()]):
        history = client.list_order_history("20260909", "20260909")
    assert history[0].requested_quantity_known is True


@pytest.mark.parametrize("status", ("new", "pending_cancel", ""))
def test_history_omits_active_notional_order_when_no_execution_is_confirmed(status: str) -> None:
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {
        **history_row(), "status": status, "qty": None, "notional": "100",
        "filled_qty": "0", "filled_avg_price": None,
    }
    with patch.object(client, "_request", return_value=[row]):
        assert client.list_order_history("20260909", "20260909") == ()
