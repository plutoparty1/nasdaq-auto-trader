import unittest
from datetime import datetime, timedelta, timezone

from nasdaq_auto_trader.market_regime import classify_market_regime
from nasdaq_auto_trader.quant_data.features import PriceBar


class MarketRegimeTests(unittest.TestCase):
    def test_broad_rising_market_is_uptrend(self):
        bars = {symbol: _bars(symbol, 0.003) for symbol in ("QQQ", "AAPL", "MSFT")}

        regime = classify_market_regime(bars)

        self.assertEqual(regime.trend, "uptrend")
        self.assertGreater(regime.market_breadth, 0.5)
        self.assertTrue(regime.trade_allowed)

    def test_insufficient_universe_forces_no_trade(self):
        regime = classify_market_regime({"QQQ": _bars("QQQ", 0.0)})

        self.assertFalse(regime.trade_allowed)
        self.assertIn("insufficient_market_breadth", regime.risk_flags)


def _bars(symbol, drift):
    start = datetime(2026, 1, 1, 21, tzinfo=timezone.utc)
    price = 100.0
    output = []
    for index in range(80):
        price *= 1 + drift
        output.append(PriceBar(symbol, (start + timedelta(days=index)).isoformat(), price, price * 1.01, price * 0.99, price, 1_000_000 + index, price - 0.01, price + 0.01))
    return output
