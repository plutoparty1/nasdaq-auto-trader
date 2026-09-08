import unittest

from nasdaq_auto_trader.broker import (
    AlpacaClient,
    AlpacaCredentials,
    BrokerOrderError,
    KISClient,
    KISCredentials,
)
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position


class BrokerCashGuardTests(unittest.TestCase):
    def test_kis_buy_boundary_blocks_order_above_deposited_cash(self):
        class FakeKISClient(KISClient):
            def get_account(self, refresh=False):
                return AccountSnapshot(cash=5, equity=1_000, buying_power=1_000)

            def get_overseas_buying_power(self, symbol, order_price=None):
                return 1_000.0

            def _request(self, method, path, tr_id, params=None, body=None):
                raise AssertionError("cash-only guard must block before POST")

        client = FakeKISClient(KISCredentials("app", "secret", "12345678"))

        with self.assertRaisesRegex(BrokerOrderError, "deposited cash"):
            client.submit_order(
                OrderRequest(
                    symbol="QQQ",
                    side="buy",
                    type="limit",
                    qty=1,
                    limit_price=500,
                )
            )

    def test_kis_buy_boundary_allows_exact_cash_and_buying_power(self):
        class FakeKISClient(KISClient):
            def __init__(self):
                super().__init__(KISCredentials("app", "secret", "12345678"))
                self.order_posts = 0

            def get_account(self, refresh=False):
                return AccountSnapshot(cash=500, equity=500, buying_power=500)

            def get_overseas_buying_power(self, symbol, order_price=None):
                return 500.0

            def _request(self, method, path, tr_id, params=None, body=None):
                self.order_posts += 1
                return {"rt_cd": "0", "output": {"ODNO": "1"}}

        client = FakeKISClient()

        response = client.submit_order(
            OrderRequest(
                symbol="QQQ",
                side="buy",
                type="limit",
                qty=1,
                limit_price=500,
            )
        )

        self.assertEqual(response["rt_cd"], "0")
        self.assertEqual(client.order_posts, 1)

    def test_kis_sell_boundary_blocks_quantity_above_fresh_holdings(self):
        class FakeKISClient(KISClient):
            def __init__(self):
                super().__init__(KISCredentials("app", "secret", "12345678"))
                self.order_posts = 0

            def list_positions(self, refresh=False):
                self.assert_refresh = refresh
                return {"AAPL": Position("AAPL", 1, 10, 10)}

            def _request(self, method, path, tr_id, params=None, body=None):
                self.order_posts += 1
                return {"rt_cd": "0"}

        client = FakeKISClient()

        with self.assertRaisesRegex(BrokerOrderError, "held quantity"):
            client.submit_order(
                OrderRequest("AAPL", "sell", qty=2, limit_price=10.0)
            )

        self.assertTrue(client.assert_refresh)
        self.assertEqual(client.order_posts, 0)

    def test_kis_sell_boundary_allows_exact_fresh_holdings(self):
        class FakeKISClient(KISClient):
            def __init__(self):
                super().__init__(KISCredentials("app", "secret", "12345678"))
                self.order_posts = 0

            def list_positions(self, refresh=False):
                return {"AAPL": Position("AAPL", 1, 10, 10)}

            def _request(self, method, path, tr_id, params=None, body=None):
                self.order_posts += 1
                return {"rt_cd": "0"}

        client = FakeKISClient()

        client.submit_order(OrderRequest("AAPL", "sell", qty=1, limit_price=10.0))

        self.assertEqual(client.order_posts, 1)

    def test_alpaca_buy_boundary_blocks_order_above_deposited_cash(self):
        class FakeAlpacaClient(AlpacaClient):
            def __init__(self):
                super().__init__(AlpacaCredentials("app", "secret", paper=False))
                self.order_posts = 0

            def _request(self, method, base_url, path, params=None, body=None):
                if path == "/v2/account":
                    return {"cash": "5", "equity": "1000", "buying_power": "1000"}
                if path == "/v2/orders":
                    self.order_posts += 1
                return {"id": "unexpected"}

        client = FakeAlpacaClient()

        with self.assertRaisesRegex(BrokerOrderError, "deposited cash"):
            client.submit_order(
                OrderRequest(
                    symbol="QQQ",
                    side="buy",
                    type="limit",
                    qty=1,
                    limit_price=500,
                )
            )

        self.assertEqual(client.order_posts, 0)

    def test_alpaca_buy_boundary_allows_exact_cash_and_buying_power(self):
        class FakeAlpacaClient(AlpacaClient):
            def __init__(self):
                super().__init__(AlpacaCredentials("app", "secret", paper=False))
                self.order_posts = 0

            def _request(self, method, base_url, path, params=None, body=None):
                if path == "/v2/account":
                    return {"cash": "500", "equity": "500", "buying_power": "500"}
                self.order_posts += 1
                return {"id": "accepted"}

        client = FakeAlpacaClient()

        response = client.submit_order(
            OrderRequest(
                symbol="QQQ",
                side="buy",
                type="limit",
                qty=1,
                limit_price=500,
            )
        )

        self.assertEqual(response["id"], "accepted")
        self.assertEqual(client.order_posts, 1)


if __name__ == "__main__":
    unittest.main()
