from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject, JsonValue
from nasdaq_auto_trader.brokers.alpaca import AlpacaClient, AlpacaCredentials
from nasdaq_auto_trader.brokers.common import BrokerRequestError


def history_row(order_id: str = "receipt-1") -> JsonObject:
    return {
        "id": order_id, "symbol": "AAPL", "side": "buy", "qty": "2",
        "filled_qty": "2", "filled_avg_price": "123.45", "status": "filled",
        "submitted_at": "2026-09-09T13:30:00.123456789Z",
    }


def test_history_preserves_status_and_aware_submission_when_dates_are_compact() -> None:
    # Given
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = history_row()
    # When
    with patch.object(client, "_request", return_value=[row]) as transport:
        history = client.list_order_history("20260909", "20260909")
    # Then
    assert history[0].status == "filled"
    assert history[0].submitted_at == datetime(
        2026, 9, 9, 13, 30, 0, 123456, timezone.utc,
    )
    assert transport.call_args.args[3]["until"] == "2026-09-10T00:00:00-04:00"


@pytest.mark.parametrize("status", ("canceled", "rejected", "expired", "new", "pending_review"))
def test_history_preserves_unfilled_status_when_average_price_is_null(status: str) -> None:
    # Given
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {**history_row(), "status": status, "filled_qty": "0", "filled_avg_price": None}
    # When
    with patch.object(client, "_request", return_value=[row]):
        history = client.list_order_history("20260909", "20260909")
    # Then
    assert (history[0].status, history[0].filled_quantity, history[0].average_fill_price) == (
        status, 0.0, 0.0,
    )


def test_history_uses_id_cursors_when_more_than_500_orders_share_submission_time() -> None:
    # Given
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    rows = [history_row(f"order-{index}") for index in range(1001)]
    # When
    with patch.object(client, "_request", side_effect=[rows[:500], rows[500:1000], rows[1000:]]) as transport:
        history = client.list_order_history("20260909", "20260909")
    # Then
    assert [item.order_id for item in history] == [f"order-{index}" for index in range(1001)]
    for call, cursor in zip(transport.call_args_list[1:], ("order-499", "order-999"), strict=True):
        assert call.args == (
            "GET", client.trading_base_url, "/v2/orders",
            {"status": "all", "limit": 500, "nested": "false", "before_order_id": cursor},
        )


def test_history_stops_at_lower_date_bound_when_cursor_page_contains_older_orders() -> None:
    # Given
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    first = [history_row(f"order-{index}") for index in range(500)]
    midnight = {**history_row("midnight"), "submitted_at": "2026-09-09T04:00:00Z"}
    older = {**history_row("older"), "submitted_at": "2026-09-09T03:59:59.999999Z"}
    # When
    with patch.object(client, "_request", side_effect=[first, [midnight, older]]) as transport:
        history = client.list_order_history("20260909", "20260909")
    # Then
    assert len(history) == 501
    assert history[-1].order_id == "midnight"
    assert transport.call_count == 2


@pytest.mark.parametrize("start,end,after,until", (
    ("20260308", "20260308", "2026-03-07T23:59:59.999999-05:00", "2026-03-09T00:00:00-04:00"),
    ("2026-11-01", "2026-11-01", "2026-10-31T23:59:59.999999-04:00", "2026-11-02T00:00:00-05:00"),
))
def test_history_uses_each_boundary_offset_when_day_crosses_dst(
    start: str, end: str, after: str, until: str,
) -> None:
    # Given
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    # When
    with patch.object(client, "_request", return_value=[]) as transport:
        history = client.list_order_history(start, end)
    # Then
    assert history == ()
    assert transport.call_args.args[3]["after"] == after
    assert transport.call_args.args[3]["until"] == until


@pytest.mark.parametrize("field,value", (
    ("id", None), ("id", " bad "), ("symbol", "AAPL "), ("side", "hold"),
    ("qty", True), ("qty", "0"), ("qty", "NaN"), ("qty", "inf"),
    ("filled_qty", None), ("filled_qty", "-1"), ("filled_qty", "3"),
    ("filled_avg_price", None), ("filled_avg_price", "0"), ("filled_avg_price", "NaN"),
    ("status", True), ("status", "surprise"),
    ("submitted_at", "2026-09-09T13:30:00"), ("submitted_at", "bad"),
))
def test_history_rejects_malformed_evidence_when_field_is_invalid(field: str, value: JsonValue) -> None:
    # Given
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    row = {**history_row(), field: value}
    # When / Then
    with patch.object(client, "_request", return_value=[row]), pytest.raises(BrokerRequestError):
        client.list_order_history("20260909", "20260909")


@pytest.mark.parametrize("payload", ({}, [None], [history_row(), history_row()]))
def test_history_rejects_invalid_page_when_shape_or_identity_is_ambiguous(payload: JsonValue) -> None:
    # Given
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    # When / Then
    with patch.object(client, "_request", return_value=payload), pytest.raises(BrokerRequestError):
        client.list_order_history("20260909", "20260909")


def test_history_rejects_repeated_page_when_cursor_does_not_advance() -> None:
    # Given
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    rows = [history_row(f"order-{index}") for index in range(500)]
    # When / Then
    with patch.object(client, "_request", side_effect=[rows, rows]), pytest.raises(BrokerRequestError):
        client.list_order_history("20260909", "20260909")


@pytest.mark.parametrize("start,end", (
    ("bad", "20260909"), ("20260230", "20260909"), ("20260910", "20260909"),
    ("2026-9-9", "20260909"), ("20260909T00:00:00", "20260909"),
    ("00010101", "00010101"), ("99991231", "99991231"),
))
def test_history_rejects_invalid_dates_before_request(start: str, end: str) -> None:
    # Given
    client = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    # When / Then
    with patch.object(client, "_request") as transport, pytest.raises(BrokerRequestError):
        client.list_order_history(start, end)
    transport.assert_not_called()
