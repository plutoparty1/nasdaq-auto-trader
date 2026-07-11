from __future__ import annotations

from tests.config_engine_fixtures import *


class ConfigEngineOrderGateTests(unittest.TestCase):
    def test_engine_dry_run_can_submit_to_injected_broker(self):
        config = AppConfig(
            mode="dry_run",
            symbols=["QQQ"],
            strategy=compact_strategy_config(),
            risk=RiskConfig(max_position_pct=0.2, risk_per_trade_pct=0),
        )
        broker = FakeBroker()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=FakeMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
        )

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "buy")
        self.assertEqual(result["order"].side, "buy")
        self.assertEqual(broker.orders[0].notional, 2000)

    def test_kis_dry_run_uses_psamount_for_buy_sizing_without_live_order(self):
        class FakeKISMarketData(FakeMarketData):
            def __init__(self):
                self.buying_power_calls = []

            def get_account(self):
                return AccountSnapshot(cash=0, equity=640, buying_power=0)

            def list_positions(self):
                return {}

            def get_overseas_buying_power(self, symbol, order_price=None):
                self.buying_power_calls.append((symbol, order_price))
                return 64

        config = AppConfig(
            mode="dry_run",
            broker="kis",
            symbols=["QQQ"],
            strategy=compact_strategy_config(),
            risk=RiskConfig(
                max_position_pct=1,
                min_cash_buffer_pct=0,
                min_order_notional=50,
                risk_per_trade_pct=0,
            ),
        )
        broker = FakeBroker()
        market_data = FakeKISMarketData()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=market_data,
            positions={},
        )

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "buy")
        self.assertEqual(result["order"].notional, 64)
        self.assertEqual(result["response"]["status"], "fake_submitted")
        self.assertEqual(broker.orders[0].notional, 64)
        self.assertEqual(result["buying_power_check"]["source"], "kis_inquire_psamount")
        self.assertEqual(market_data.buying_power_calls[0][0], "QQQ")

    def test_kis_dry_run_honors_configured_api_environment(self):
        config = AppConfig(
            mode="dry_run",
            broker="kis",
            kis=KISCredentials(
                app_key="app",
                app_secret="secret",
                account_no="12345678",
                paper=False,
            ),
        )

        engine = TradingEngine(config)

        self.assertIsInstance(engine.market_data, KISClient)
        self.assertFalse(engine.market_data.credentials.paper)

    def test_live_capable_order_is_blocked_outside_regular_market_hours(self):
        config = AppConfig(
            mode="paper",
            symbols=["QQQ"],
            alpaca=AlpacaCredentials("key", "secret"),
            strategy=compact_strategy_config(),
            risk=RiskConfig(max_position_pct=0.2, risk_per_trade_pct=0),
        )
        broker = FakeBroker()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=FakeMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            clock=lambda: datetime(2026, 6, 27, 14, 0, tzinfo=timezone.utc),
        )

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "buy")
        self.assertEqual(len(broker.orders), 0)
        self.assertEqual(result["response"]["status"], "blocked")
        self.assertEqual(result["response"]["reason"], "regular_market_closed")

    def test_live_capable_order_is_allowed_inside_regular_market_hours(self):
        config = AppConfig(
            mode="paper",
            symbols=["QQQ"],
            alpaca=AlpacaCredentials("key", "secret"),
            strategy=compact_strategy_config(),
            risk=RiskConfig(max_position_pct=0.2, risk_per_trade_pct=0),
        )
        broker = FakeBroker()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=FakeMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            clock=lambda: datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
        )

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "buy")
        self.assertEqual(result["response"]["status"], "fake_submitted")
        self.assertEqual(len(broker.orders), 1)

    def test_live_order_blocks_without_final_confirmation(self):
        config = AppConfig(
            mode="live",
            allow_live_trading=True,
            live_environment_authorized=True,
            regular_market_hours_only=False,
            symbols=["QQQ"],
            alpaca=AlpacaCredentials("key", "secret", paper=False),
            strategy=compact_strategy_config(),
            risk=RiskConfig(max_position_pct=0.2, risk_per_trade_pct=0),
        )
        broker = FakeBroker()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=FakeMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
        )

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "buy")
        self.assertEqual(result["response"]["status"], "blocked")
        self.assertEqual(result["response"]["reason"], "live_order_confirmation_required")
        self.assertEqual(broker.orders, [])
