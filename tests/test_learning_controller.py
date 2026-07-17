import unittest
from unittest.mock import patch

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from tests.app_controller_fixtures import IsolatedControllerTestCase


class RecordingMarketData:
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        del symbols, timeframe, start, end, limit
        return {}


class LearningEngine:
    def __init__(self) -> None:
        self.market_data = RecordingMarketData()


class LearningControllerTests(IsolatedControllerTestCase):
    def test_automatic_selection_learning_uses_packaged_nasdaq_100_universe(self):
        controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ", "AAPL"]),
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                ),
                session_store=self.session_store(),
            )
        with (
            patch.object(
                controller,
                "_create_engine",
                return_value=LearningEngine(),
            ),
            patch(
                "nasdaq_auto_trader.controller_operations.collect_completed_learning_bars",
                return_value={},
            ) as collect,
        ):
            result = controller.run_learning_only()

        learning_config = collect.call_args.args[0]
        self.assertGreaterEqual(len(learning_config.symbols), 100)
        self.assertIn("AAPL", learning_config.symbols)
        self.assertIn("MSFT", learning_config.symbols)
        self.assertEqual(result.submitted_orders, 0)


if __name__ == "__main__":
    unittest.main()
