from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.request import Request

from nasdaq_auto_trader.broker import KISCredentials
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.brokers.kis_client import KISClient
from nasdaq_auto_trader.live_canary_preflight import (
    KISPreflightTransportClient,
    PreflightResult,
    ReadOnlyPreflightClient,
    run_preflight,
)
from nasdaq_auto_trader.models import AccountSnapshot, Position


class ReadOnlyClient:
    def __init__(self, positions=None, orders=(), cash=20.0) -> None:
        self.positions = positions or {}
        self.orders = orders
        self.cash = cash
        self.calls: list[str] = []

    def get_account(self, refresh: bool = False):
        self.calls.append("account")
        return AccountSnapshot(self.cash, self.cash, self.cash)

    def list_positions(self, refresh: bool = False):
        self.calls.append("positions")
        return self.positions

    def list_open_orders(self):
        self.calls.append("open_orders")
        return self.orders

    def submit_order(self, order):
        raise AssertionError("preflight must never call a POST-capable method")


class LiveCanaryPreflightTests(unittest.TestCase):
    def test_transport_rejects_order_and_non_allowlisted_endpoints(self):
        client = KISPreflightTransportClient(
            KISCredentials("app", "secret", "12345678")
        )

        for request in (
            Request("https://example.test/uapi/overseas-stock/v1/trading/order", method="POST"),
            Request("https://example.test/uapi/overseas-stock/v1/quotations/price", method="GET"),
        ):
            with self.assertRaisesRegex(BrokerRequestError, "preflight_transport_not_allowed"):
                client._open_json(request, "blocked")

    @patch.object(KISClient, "_open_json", return_value={"rt_cd": "0"})
    def test_transport_allows_only_expected_account_gets_and_oauth(
        self,
        open_json,
    ):
        client = KISPreflightTransportClient(
            KISCredentials("app", "secret", "12345678")
        )
        allowed = (
            ("POST", "/oauth2/tokenP"),
            ("GET", "/uapi/overseas-stock/v1/trading/inquire-present-balance"),
            ("GET", "/uapi/overseas-stock/v1/trading/inquire-balance"),
            ("GET", "/uapi/overseas-stock/v1/trading/inquire-nccs"),
        )

        for method, path in allowed:
            self.assertEqual(
                client._open_json(Request(f"https://example.test{path}", method=method), "allowed"),
                {"rt_cd": "0"},
            )

        self.assertEqual(open_json.call_count, len(allowed))

    def test_read_only_wrapper_exposes_no_order_methods(self):
        wrapped = ReadOnlyPreflightClient(ReadOnlyClient())

        self.assertFalse(hasattr(wrapped, "submit_order"))
        self.assertFalse(hasattr(wrapped, "cancel_order"))

    def test_get_only_preflight_passes_empty_account_with_cash_gate(self):
        client = ReadOnlyClient()

        result = run_preflight(client)

        self.assertEqual(result, PreflightResult(True, True, 0, 0, ()))
        self.assertEqual(client.calls, ["account", "positions", "open_orders"])

    def test_preflight_fails_closed_on_foreign_position_or_order(self):
        client = ReadOnlyClient(
            positions={"AAPL": Position("AAPL", 1, 10, 10)},
            orders=(object(),),
        )

        result = run_preflight(client)

        self.assertFalse(result.ready)
        self.assertEqual(result.blockers, ("existing_position", "existing_open_order"))

    def test_preflight_requires_twenty_dollars_deposited_cash(self):
        result = run_preflight(ReadOnlyClient(cash=19.99))

        self.assertFalse(result.ready)
        self.assertEqual(result.blockers, ("cash_below_canary_gate",))


if __name__ == "__main__":
    unittest.main()
