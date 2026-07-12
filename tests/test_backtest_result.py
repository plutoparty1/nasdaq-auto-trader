import unittest
from dataclasses import FrozenInstanceError

from nasdaq_auto_trader.backtest import Backtester
from nasdaq_auto_trader.backtest import BacktestResult, BacktestTrade, EquityPoint
from nasdaq_auto_trader.risk import RiskManager
from nasdaq_auto_trader.strategy import TechnicalStrategy


class BacktestResultTests(unittest.TestCase):
    def test_result_objects_are_frozen_slotted_and_tuple_backed(self):
        trade = BacktestTrade("T030", "T031", "QQQ", "buy", 100.0, 1.0, 100.0, ("entry",))
        result = BacktestResult(
            100.0,
            101.0,
            (trade,),
            (EquityPoint("T031", 101.0, 1.0, 100.0),),
        )

        self.assertFalse(hasattr(result, "__dict__"))
        self.assertEqual(result.trades[0].reasons, ("entry",))
        with self.assertRaises(FrozenInstanceError):
            result.ending_value = 102.0

    def test_backtester_rejects_invalid_starting_cash(self):
        backtester = Backtester(TechnicalStrategy(), RiskManager())

        for starting_cash in (0, -1, float("nan"), float("inf")):
            with self.subTest(starting_cash=starting_cash):
                with self.assertRaisesRegex(ValueError, "starting_cash"):
                    backtester.run({}, starting_cash=starting_cash)


if __name__ == "__main__":
    unittest.main()
