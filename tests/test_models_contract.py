import unittest

from nasdaq_auto_trader.models import (
    AccountSnapshot,
    Bar,
    OrderRequest,
    OrderRequestPayloadError,
    Position,
    TradeDecision,
)


class ModelContractTests(unittest.TestCase):
    def test_core_models_are_slotted(self):
        instances = (
            Bar("QQQ", "T1", 1.0, 2.0, 0.5, 1.5, 1000.0),
            Position("QQQ", 1.0, 101.0, 100.0),
            AccountSnapshot(100.0, 101.0, 100.0),
            TradeDecision("QQQ", "hold", 0, 101.0),
            OrderRequest("QQQ", "buy", notional=123.456),
        )

        for instance in instances:
            with self.subTest(model=type(instance).__name__):
                self.assertFalse(hasattr(instance, "__dict__"))

    def test_order_request_payload_keeps_alpaca_wire_shape(self):
        payload = OrderRequest(
            symbol="QQQ",
            side="buy",
            type="limit",
            qty=3,
            limit_price=179.01234,
        ).to_alpaca_payload()

        self.assertEqual(
            payload,
            {
                "symbol": "QQQ",
                "side": "buy",
                "type": "limit",
                "time_in_force": "day",
                "qty": "3",
                "limit_price": "179.0123",
            },
        )

    def test_order_request_rejects_qty_and_notional_in_same_alpaca_payload(self):
        order = OrderRequest(symbol="QQQ", side="buy", qty=3, notional=537.04)

        with self.assertRaisesRegex(
            OrderRequestPayloadError,
            "qty and notional are mutually exclusive",
        ):
            order.to_alpaca_payload()


if __name__ == "__main__":
    unittest.main()
