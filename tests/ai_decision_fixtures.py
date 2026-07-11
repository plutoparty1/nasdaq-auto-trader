import json

from nasdaq_auto_trader.models import Bar
from nasdaq_auto_trader.strategy import StrategyConfig


class StaticAIProviderExhaustedError(RuntimeError):
    pass


class StaticAIProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request_ai_recommendation(self, prompt, context):
        self.calls.append((prompt, context))
        if not self.responses:
            raise StaticAIProviderExhaustedError
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeBroker:
    def __init__(self):
        self.orders = []

    def submit_order(self, order):
        self.orders.append(order)
        return {"status": "fake_submitted"}


class MultiSymbolMarketData:
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        return {symbol: uptrend_bars(symbol) for symbol in symbols}


def ai_json(**overrides):
    payload = {
        "action": "buy",
        "ticker": "NVDA",
        "order_qty": 1,
        "confidence": 0.82,
        "reason": "단기 추세와 거래량이 양호함",
        "risk": "장중 변동성이 높음",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def uptrend_bars(symbol):
    bars = []
    for index in range(80):
        close = 100 + index
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=f"T{index + 1:03d}",
                open=close - 0.5,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1_000_000 + index,
            )
        )
    return bars


def compact_strategy():
    return StrategyConfig(
        sma_fast=5,
        sma_slow=20,
        ema_fast=6,
        ema_slow=13,
        macd_fast=6,
        macd_slow=13,
        macd_signal=5,
        long_sma=30,
        momentum_period=10,
        donchian_period=20,
        buy_score=5,
        sell_score=4,
    )
