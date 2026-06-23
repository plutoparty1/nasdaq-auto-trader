import sys
import unittest
from pathlib import Path


# 테스트가 로컬 패키지를 설치 없이 읽도록 경로를 추가한다.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig, validate_trading_mode
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Bar, OrderRequest
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.strategy import StrategyConfig


class FakeBroker:
    # 실제 주문을 보내지 않고 테스트 안에만 저장한다.
    def __init__(self):
        self.orders = []

    def submit_order(self, order):
        self.orders.append(order)
        return {"status": "fake_submitted"}


class FakeMarketData:
    # 엔진이 시세 API 없이도 테스트되도록 고정 봉 데이터를 돌려준다.
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        bars = []
        for index in range(60):
            close = 100 + index
            bars.append(
                Bar(
                    symbol="QQQ",
                    timestamp=f"2026-02-{index + 1:02d}",
                    open=close - 0.5,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=1_000_000,
                )
            )
        return {"QQQ": bars}


class ConfigAndEngineTests(unittest.TestCase):
    def test_live_mode_requires_explicit_allow_flag(self):
        # live 모드는 키가 있어도 별도 허용값이 없으면 막아야 한다.
        config = AppConfig(
            mode="live",
            allow_live_trading=False,
            alpaca=AlpacaCredentials("key", "secret", paper=False),
        )

        with self.assertRaises(ValueError):
            validate_trading_mode(config)

    def test_order_payload_uses_alpaca_shape(self):
        # 내부 주문 객체는 Alpaca가 받는 문자열 기반 JSON으로 바뀌어야 한다.
        payload = OrderRequest(symbol="QQQ", side="buy", notional=123.456).to_alpaca_payload()

        self.assertEqual(payload["symbol"], "QQQ")
        self.assertEqual(payload["side"], "buy")
        self.assertEqual(payload["notional"], "123.46")

    def test_engine_dry_run_can_submit_to_injected_broker(self):
        # dry-run 엔진은 주입한 가짜 시세와 가짜 브로커만으로 매수 주문을 만든다.
        config = AppConfig(
            mode="dry_run",
            symbols=["QQQ"],
            strategy=StrategyConfig(buy_score=3),
            risk=RiskConfig(max_position_pct=0.2),
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


if __name__ == "__main__":
    unittest.main()
