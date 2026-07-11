import unittest

from tests.ai_decision_fixtures import MultiSymbolMarketData, compact_strategy

from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSessionState
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.risk import RiskConfig


class RejectingBroker:
    def __init__(self) -> None:
        self.orders = []
        self.response = {
            "id": "broker-order-1",
            "status": "rejected",
            "reason": "insufficient_buying_power",
        }

    def submit_order(self, order):
        self.orders.append(order)
        return self.response


class EngineBrokerResponseTests(unittest.TestCase):
    def test_rejected_broker_response_does_not_count_as_submitted_order(self):
        session_state = TradingSessionState()
        broker = RejectingBroker()
        engine = TradingEngine(
            AppConfig(
                mode="paper",
                regular_market_hours_only=False,
                symbols=["QQQ"],
                alpaca=AlpacaCredentials("key", "secret"),
                strategy=compact_strategy(),
                risk=RiskConfig(max_position_pct=0.2, risk_per_trade_pct=0),
            ),
            broker=broker,
            market_data=MultiSymbolMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            trading_session_state=session_state,
        )

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "buy")
        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(result["response"]["status"], "blocked")
        self.assertEqual(
            result["response"]["reason"],
            "order_response_not_submitted:rejected",
        )
        self.assertEqual(result["response"]["broker_response"], broker.response)
        self.assertEqual(session_state.buy_count, 0)
        self.assertIsNone(session_state.last_order_at)


if __name__ == "__main__":
    unittest.main()
