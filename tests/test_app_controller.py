import unittest
from datetime import datetime, timezone

from nasdaq_auto_trader.app import AutoTradeController
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position


class FakeEngine:
    def __init__(self):
        self.run_count = 0
        self.refresh_flags = []

    def run_once(self):
        self.run_count += 1
        return [
            {
                "symbol": "QQQ",
                "decision": None,
                "order": None,
                "response": {"status": "fake"},
                "account": AccountSnapshot(cash=100, equity=120, buying_power=80),
                "buying_power_check": None,
                "trading_agents": None,
            }
        ]

    def load_portfolio(self, refresh=False):
        self.refresh_flags.append(refresh)
        return (
            AccountSnapshot(cash=100, equity=120, buying_power=80),
            {
                "QQQ": Position(
                    symbol="QQQ",
                    qty=2,
                    market_value=120,
                    avg_entry_price=50,
                )
            },
        )


class FakeEngineFactory:
    def __init__(self):
        self.instances = []

    def __call__(self, config):
        engine = FakeEngine()
        self.instances.append(engine)
        return engine


class RefreshBroker:
    def __init__(self):
        self.account_refresh = None
        self.positions_refresh = None

    def submit_order(self, order):
        return {"status": "unused"}

    def get_account(self, refresh=False):
        self.account_refresh = refresh
        return AccountSnapshot(cash=10, equity=11, buying_power=9)

    def list_positions(self, refresh=False):
        self.positions_refresh = refresh
        return {
            "QQQ": Position(
                symbol="QQQ",
                qty=1,
                market_value=11,
                avg_entry_price=10,
            )
        }


class StaticMarketData:
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        return {
            symbol: [
                Bar(
                    symbol=symbol,
                    timestamp="T001",
                    open=10,
                    high=11,
                    low=9,
                    close=10,
                    volume=1000,
                )
            ]
            for symbol in symbols
        }


class AppControllerTests(unittest.TestCase):
    def test_refresh_portfolio_builds_rows_from_latest_broker_state(self):
        factory = FakeEngineFactory()
        controller = AutoTradeController(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=factory,
            clock=lambda: datetime(2026, 6, 30, 1, 2, tzinfo=timezone.utc),
        )

        snapshot = controller.refresh_portfolio()

        self.assertEqual(snapshot.account.cash, 100)
        self.assertEqual(snapshot.positions[0].symbol, "QQQ")
        self.assertEqual(snapshot.positions[0].latest_price, 60)
        self.assertEqual(snapshot.positions[0].unrealized_pl, 20)
        self.assertEqual(snapshot.positions[0].unrealized_pl_pct, 20)
        self.assertEqual(factory.instances[0].refresh_flags, [True])

    def test_start_pause_and_resume_gate_auto_cycles(self):
        factory = FakeEngineFactory()
        controller = AutoTradeController(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=factory,
            clock=lambda: datetime(2026, 6, 30, 1, 2, tzinfo=timezone.utc),
        )

        controller.start(interval_seconds=60)
        first_result = controller.run_auto_cycle(force=True)
        controller.pause()
        paused_result = controller.run_auto_cycle(force=True)
        controller.resume()
        resumed_result = controller.run_auto_cycle(force=True)

        self.assertEqual(controller.state, "running")
        self.assertEqual(len(first_result), 1)
        self.assertIsNone(paused_result)
        self.assertEqual(len(resumed_result), 1)
        self.assertEqual(len(factory.instances), 2)

    def test_trading_engine_load_portfolio_passes_refresh_to_broker(self):
        broker = RefreshBroker()
        engine = TradingEngine(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            broker=broker,
            market_data=StaticMarketData(),
        )

        account, positions = engine.load_portfolio(refresh=True)

        self.assertEqual(account.cash, 10)
        self.assertEqual(positions["QQQ"].market_value, 11)
        self.assertTrue(broker.account_refresh)
        self.assertTrue(broker.positions_refresh)


if __name__ == "__main__":
    unittest.main()
