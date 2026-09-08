import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nasdaq_auto_trader.indicators import (
    IndicatorInputError,
    atr,
    bollinger_bands,
    donchian_channel,
    ema,
    macd,
    rate_of_change,
    rsi,
    sma,
    stochastic_oscillator,
)
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position, TradeDecision
from nasdaq_auto_trader.risk import RiskConfig, RiskManager
from nasdaq_auto_trader.strategy import StrategyConfig, TechnicalStrategy


def strategy_config_fixture(**overrides):
    defaults = {
        "sma_fast": 5,
        "sma_slow": 20,
        "ema_fast": 6,
        "ema_slow": 13,
        "rsi_period": 14,
        "macd_fast": 6,
        "macd_slow": 13,
        "macd_signal": 5,
        "bollinger_period": 20,
        "long_sma": 30,
        "momentum_period": 10,
        "donchian_period": 20,
        "stochastic_period": 14,
        "volume_period": 20,
        "atr_period": 14,
        "buy_score": 5,
        "sell_score": 4,
    }
    defaults.update(overrides)
    return StrategyConfig(**defaults)


class IndicatorTests(unittest.TestCase):
    def test_invalid_inputs_raise_typed_indicator_error(self):
        with self.assertRaisesRegex(IndicatorInputError, "period must be greater"):
            sma([1, 2, 3], 0)
        with self.assertRaisesRegex(IndicatorInputError, "undefined"):
            rate_of_change([0, 1], 1)

    def test_core_indicators_follow_expected_direction(self):
        self.assertEqual(sma([1, 2, 3, 4, 5], 3), 4)
        self.assertGreater(ema([10, 11, 12, 13, 14], 3), 12)
        self.assertGreater(rsi([1, 2, 3, 4, 5, 6, 7, 8], 5), 70)

        lower, middle, upper = bollinger_bands([10, 11, 12, 13, 14], 5)
        self.assertLess(lower, middle)
        self.assertLess(middle, upper)

    def test_macd_turns_positive_on_uptrend(self):
        closes = [100 + index + index * index * 0.05 for index in range(50)]
        line, signal, histogram = macd(closes, fast=6, slow=13, signal=5)
        self.assertGreater(line, signal)
        self.assertGreater(histogram, 0)

    def test_breakout_momentum_volatility_indicators(self):
        bars = [
            Bar("QQQ", f"2026-01-{index + 1:02d}", close - 1, close + 2, close - 2, close, 1000)
            for index, close in enumerate(range(100, 121))
        ]

        self.assertAlmostEqual(rate_of_change([100, 110, 121], 2), 21)
        self.assertEqual(donchian_channel([9, 11, 10, 13], 3), (10, 13))
        self.assertGreater(stochastic_oscillator(bars, 14), 80)
        self.assertGreater(atr(bars, 14), 0)


class StrategyAndRiskTests(unittest.TestCase):
    def test_strategy_config_is_slotted(self):
        self.assertFalse(hasattr(strategy_config_fixture(), "__dict__"))

    def _bars(self, closes):
        return [
            Bar(
                symbol="QQQ",
                timestamp=f"2026-01-{index + 1:02d}",
                open=close - 0.5,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1_000_000 + index,
            )
            for index, close in enumerate(closes)
        ]

    def test_strategy_buys_strong_mechanical_uptrend(self):
        bars = self._bars(range(100, 170))
        strategy = TechnicalStrategy(strategy_config_fixture())

        decision = strategy.decide("QQQ", bars, None)

        self.assertEqual(decision.action, "buy")
        self.assertGreaterEqual(decision.score, 5)
        self.assertIn("long_regime_up", decision.reasons)
        self.assertIn("donchian_breakout", decision.reasons)
        self.assertIsNotNone(decision.risk_per_share)

    def test_strategy_sells_when_stop_loss_is_hit(self):
        bars = self._bars([100] * 30 + [90])
        strategy = TechnicalStrategy(strategy_config_fixture(stop_loss_pct=0.05))
        position = Position(symbol="QQQ", qty=10, market_value=900, avg_entry_price=100)

        decision = strategy.decide("QQQ", bars, position)

        self.assertEqual(decision.action, "sell")
        self.assertIn("fixed_stop_loss", decision.reasons)

    def test_position_mark_triggers_take_profit_before_bar_close_catches_up(self):
        bars = self._bars([25.8] * 30 + [27.075])
        strategy = TechnicalStrategy(strategy_config_fixture(take_profit_pct=0.05))
        position = Position(
            symbol="WBD",
            qty=1,
            market_value=27.18,
            avg_entry_price=25.795,
        )

        decision = strategy.decide("WBD", bars, position)

        self.assertEqual(decision.action, "sell")
        self.assertEqual(decision.latest_price, 27.18)
        self.assertIn("fixed_take_profit", decision.reasons)

    def test_risk_manager_caps_buy_notional(self):
        manager = RiskManager(
            RiskConfig(
                max_position_pct=0.2,
                min_cash_buffer_pct=0.1,
                risk_per_trade_pct=0,
            )
        )
        account = AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000)
        decision = TechnicalStrategy(strategy_config_fixture()).decide(
            "QQQ",
            self._bars(range(100, 170)),
            None,
        )

        order = manager.build_order(decision, account, None, latest_price=169)

        self.assertEqual(order.side, "buy")
        self.assertEqual(order.notional, 2000)

    def test_risk_manager_uses_per_trade_risk_distance(self):
        manager = RiskManager(
            RiskConfig(
                max_position_pct=1.0,
                min_cash_buffer_pct=0,
                risk_per_trade_pct=0.01,
            )
        )
        account = AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000)
        decision = TradeDecision("QQQ", "buy", 10, 100, ["test"], risk_per_share=20)

        order = manager.build_order(decision, account, None, latest_price=100)

        self.assertEqual(order.notional, 500)

    def test_fixed_quantity_buy_is_blocked_when_cash_is_below_order_value(self):
        # Given margin-like buying power covers one share but deposited cash does not.
        manager = RiskManager(RiskConfig(order_qty=1, min_cash_to_buy=0))
        account = AccountSnapshot(cash=10, equity=1_000, buying_power=1_000)
        decision = TradeDecision("QQQ", "buy", 10, 500, ["test"])

        # When the fixed-quantity order is built.
        order = manager.build_order(decision, account, None, latest_price=500)

        # Then no buy can be created from borrowed buying power.
        self.assertIsNone(order)

    def test_fixed_quantity_buy_uses_limit_price_as_cash_spending_ceiling(self):
        manager = RiskManager(RiskConfig(order_qty=1, min_cash_to_buy=0))
        account = AccountSnapshot(cash=500, equity=1_000, buying_power=1_000)
        decision = TradeDecision("QQQ", "buy", 10, 500, ["test"])

        order = manager.build_order(decision, account, None, latest_price=500)

        self.assertEqual(order.type, "limit")
        self.assertEqual(order.limit_price, 500)


if __name__ == "__main__":
    unittest.main()
