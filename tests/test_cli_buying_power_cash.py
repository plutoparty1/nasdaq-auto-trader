import unittest
from unittest.mock import patch

from nasdaq_auto_trader.cli_commands_basic import _run_buying_power_check
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.models import AccountSnapshot


class BuyingPowerCashTests(unittest.TestCase):
    def test_buy_possible_is_false_when_deposited_cash_is_insufficient(self):
        class FakeClient:
            def get_latest_price(self, symbol):
                return 10.0

            def get_overseas_buying_power(self, symbol, order_price=None):
                return 1000.0

            def get_account(self, refresh=False):
                return AccountSnapshot(cash=5.0, equity=5.0, buying_power=5.0)

            def list_positions(self, refresh=False):
                return {}

        class FakeEngine:
            def __init__(self, config):
                self.market_data = FakeClient()

        with patch(
            "nasdaq_auto_trader.cli_commands_basic.TradingEngine",
            FakeEngine,
        ):
            result = _run_buying_power_check(
                AppConfig(broker="kis", symbols=["QQQ"]),
                "QQQ",
                1.0,
            )

        self.assertFalse(result["buy_possible"])


if __name__ == "__main__":
    unittest.main()
