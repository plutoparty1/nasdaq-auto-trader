import sys
import unittest
from pathlib import Path


# 테스트는 아직 설치하지 않은 로컬 패키지를 바로 읽기 위해 경로를 추가한다.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nasdaq_auto_trader.indicators import bollinger_bands, ema, macd, rsi, sma
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position
from nasdaq_auto_trader.risk import RiskConfig, RiskManager
from nasdaq_auto_trader.strategy import StrategyConfig, TechnicalStrategy


class IndicatorTests(unittest.TestCase):
    def test_core_indicators_follow_expected_direction(self):
        # 단순 이동평균은 마지막 기간의 평균을 돌려주어야 한다.
        self.assertEqual(sma([1, 2, 3, 4, 5], 3), 4)

        # 상승장이면 EMA가 단순히 첫 값에 머물지 않고 위로 따라가야 한다.
        self.assertGreater(ema([10, 11, 12, 13, 14], 3), 12)

        # 계속 오른 가격은 RSI가 강하게 나와야 한다.
        self.assertGreater(rsi([1, 2, 3, 4, 5, 6, 7, 8], 5), 70)

        # 볼린저 밴드는 중간선이 평균이고 위/아래 밴드 순서가 맞아야 한다.
        lower, middle, upper = bollinger_bands([10, 11, 12, 13, 14], 5)
        self.assertLess(lower, middle)
        self.assertLess(middle, upper)

    def test_macd_turns_positive_on_uptrend(self):
        # 상승 속도가 빨라지면 MACD 선이 신호선보다 위에 있어야 한다.
        closes = [100 + index + index * index * 0.05 for index in range(50)]
        line, signal, histogram = macd(closes, fast=6, slow=13, signal=5)
        self.assertGreater(line, signal)
        self.assertGreater(histogram, 0)


class StrategyAndRiskTests(unittest.TestCase):
    def _bars(self, closes):
        # 전략 테스트용 봉 데이터를 빠르게 만든다.
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
        # 유명 지표들이 동시에 상승을 가리키면 매수 판단을 내린다.
        bars = self._bars(range(100, 160))
        strategy = TechnicalStrategy(
            StrategyConfig(
                sma_fast=5,
                sma_slow=20,
                ema_fast=6,
                ema_slow=13,
                rsi_period=14,
                macd_fast=6,
                macd_slow=13,
                macd_signal=5,
                buy_score=3,
                sell_score=2,
            )
        )

        decision = strategy.decide("QQQ", bars, None)

        self.assertEqual(decision.action, "buy")
        self.assertGreaterEqual(decision.score, 3)
        self.assertIn("sma_trend", decision.reasons)

    def test_strategy_sells_when_stop_loss_is_hit(self):
        # 보유 중인 종목이 손절선 아래로 내려가면 매도 판단을 내린다.
        bars = self._bars([100] * 30 + [90])
        strategy = TechnicalStrategy(StrategyConfig(stop_loss_pct=0.05))
        position = Position(symbol="QQQ", qty=10, market_value=900, avg_entry_price=100)

        decision = strategy.decide("QQQ", bars, position)

        self.assertEqual(decision.action, "sell")
        self.assertIn("stop_loss", decision.reasons)

    def test_risk_manager_caps_buy_notional(self):
        # 위험관리는 한 종목에 너무 많은 돈을 넣지 못하게 주문 금액을 자른다.
        manager = RiskManager(RiskConfig(max_position_pct=0.2, min_cash_buffer_pct=0.1))
        account = AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000)
        decision = TechnicalStrategy().decide("QQQ", self._bars(range(100, 160)), None)

        order = manager.build_order(decision, account, None, latest_price=150)

        self.assertEqual(order.side, "buy")
        self.assertEqual(order.notional, 2000)


if __name__ == "__main__":
    unittest.main()
