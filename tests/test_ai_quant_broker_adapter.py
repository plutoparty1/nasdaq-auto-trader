import unittest

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.execution.live_integration import ExistingBrokerOrderAdapter
from nasdaq_auto_trader.execution.risk_guard import OrderIntent
from nasdaq_auto_trader.models import OrderRequest


class AIQuantBrokerAdapterTests(unittest.TestCase):
    def test_broker_adapter_requires_explicit_success_marker(self):
        class MissingStatusBroker:
            def submit_order(self, order: OrderRequest) -> JsonObject:
                del order
                return {}

        response = ExistingBrokerOrderAdapter(MissingStatusBroker()).submit_order(
            OrderIntent("strategy-1", "QQQ", "buy", 1, 100.0, 100.0)
        )

        self.assertEqual(response["status"], "order_response_missing_status")

    def test_broker_adapter_rejects_explicit_failure_status_even_with_order_id(self):
        class RejectedStatusBroker:
            def submit_order(self, order: OrderRequest) -> JsonObject:
                del order
                return {
                    "id": "broker-order-1",
                    "status": "rejected",
                    "reason": "insufficient_buying_power",
                }

        response = ExistingBrokerOrderAdapter(RejectedStatusBroker()).submit_order(
            OrderIntent("strategy-1", "QQQ", "buy", 1, 100.0, 100.0)
        )

        self.assertEqual(response["status"], "rejected")
        self.assertEqual(response["broker_status"], "rejected")

    def test_broker_adapter_submits_limit_order_on_reviewed_price_surface(self):
        broker = _AcceptedBroker()

        response = ExistingBrokerOrderAdapter(broker).submit_order(
            OrderIntent("strategy-1", "QQQ", "buy", 3, 179.01234, 537.04)
        )

        self.assertEqual(response["status"], "submitted")
        self.assertEqual(len(broker.orders), 1)
        order = broker.orders[0]
        self.assertEqual(order.type, "limit")
        self.assertEqual(order.qty, 3.0)
        self.assertIsNone(order.notional)
        self.assertEqual(order.limit_price, 179.01234)
        self.assertEqual(
            order.to_alpaca_payload(),
            {
                "symbol": "QQQ",
                "side": "buy",
                "type": "limit",
                "time_in_force": "day",
                "qty": "3.0",
                "limit_price": "179.0123",
            },
        )


class _AcceptedBroker:
    def __init__(self) -> None:
        self.orders: list[OrderRequest] = []

    def submit_order(self, order: OrderRequest) -> JsonObject:
        self.orders.append(order)
        return {"id": "broker-order-1", "status": "accepted"}


if __name__ == "__main__":
    unittest.main()
