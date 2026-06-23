"""기술적 지표 점수를 기계적으로 합쳐 매매 판단을 만든다."""

from __future__ import annotations

from dataclasses import dataclass

from .indicators import bollinger_bands, ema, macd, rsi, sma
from .models import Bar, Position, TradeDecision


@dataclass(frozen=True)
class StrategyConfig:
    """전략에 쓰는 지표 기간과 점수 기준을 담는다."""

    sma_fast: int = 20
    sma_slow: int = 50
    ema_fast: int = 12
    ema_slow: int = 26
    rsi_period: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    buy_score: int = 3
    sell_score: int = 3
    stop_loss_pct: float = 0.07
    take_profit_pct: float = 0.18


class TechnicalStrategy:
    """여러 유명 지표를 점수로 합쳐 자동 판단을 낸다."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        """설정이 없으면 보수적인 기본값을 사용한다."""

        self.config = config or StrategyConfig()

    def decide(
        self,
        symbol: str,
        bars: list[Bar],
        position: Position | None,
    ) -> TradeDecision:
        """한 종목의 최근 봉과 보유 상태를 보고 다음 행동을 정한다."""

        if not bars:
            return TradeDecision(symbol, "hold", 0, 0, ["no_data"])

        closes = [bar.close for bar in bars]
        latest_price = closes[-1]
        if position is not None:
            stop_decision = self._position_guard(symbol, latest_price, position)
            if stop_decision is not None:
                return stop_decision

        minimum_bars = max(
            self.config.sma_slow,
            self.config.ema_slow,
            self.config.rsi_period + 1,
            self.config.macd_slow + self.config.macd_signal,
            self.config.bollinger_period,
        )
        if len(bars) < minimum_bars:
            return TradeDecision(symbol, "hold", 0, latest_price, ["not_enough_data"])

        buy_score, buy_reasons = self._buy_score(closes, latest_price)
        sell_score, sell_reasons = self._sell_score(closes, latest_price)

        if position is None and buy_score >= self.config.buy_score:
            return TradeDecision(symbol, "buy", buy_score, latest_price, buy_reasons)

        if position is not None and sell_score >= self.config.sell_score:
            return TradeDecision(symbol, "sell", sell_score, latest_price, sell_reasons)

        reasons = buy_reasons if position is None else sell_reasons
        score = buy_score if position is None else sell_score
        return TradeDecision(symbol, "hold", score, latest_price, reasons or ["no_signal"])

    def _position_guard(
        self,
        symbol: str,
        latest_price: float,
        position: Position,
    ) -> TradeDecision | None:
        """손절과 익절처럼 가장 먼저 확인해야 하는 규칙을 처리한다."""

        entry = position.avg_entry_price
        if latest_price <= entry * (1 - self.config.stop_loss_pct):
            return TradeDecision(symbol, "sell", 99, latest_price, ["stop_loss"])
        if latest_price >= entry * (1 + self.config.take_profit_pct):
            return TradeDecision(symbol, "sell", 90, latest_price, ["take_profit"])
        return None

    def _buy_score(self, closes: list[float], latest_price: float) -> tuple[int, list[str]]:
        """매수 쪽 지표 점수를 계산한다."""

        score = 0
        reasons: list[str] = []

        if sma(closes, self.config.sma_fast) > sma(closes, self.config.sma_slow):
            if latest_price > sma(closes, self.config.sma_slow):
                score += 2
                reasons.append("sma_trend")

        if ema(closes, self.config.ema_fast) > ema(closes, self.config.ema_slow):
            score += 1
            reasons.append("ema_trend")

        macd_line, signal_line, histogram = macd(
            closes,
            self.config.macd_fast,
            self.config.macd_slow,
            self.config.macd_signal,
        )
        if macd_line > signal_line and histogram > 0:
            score += 1
            reasons.append("macd_positive")

        rsi_value = rsi(closes, self.config.rsi_period)
        if 45 <= rsi_value <= self.config.rsi_overbought:
            score += 1
            reasons.append("rsi_trend")

        lower, _middle, _upper = bollinger_bands(closes, self.config.bollinger_period)
        if latest_price <= lower:
            score += 1
            reasons.append("bollinger_reversion")

        return score, reasons

    def _sell_score(self, closes: list[float], latest_price: float) -> tuple[int, list[str]]:
        """매도 쪽 지표 점수를 계산한다."""

        score = 0
        reasons: list[str] = []

        if sma(closes, self.config.sma_fast) < sma(closes, self.config.sma_slow):
            if latest_price < sma(closes, self.config.sma_slow):
                score += 2
                reasons.append("sma_downtrend")

        if ema(closes, self.config.ema_fast) < ema(closes, self.config.ema_slow):
            score += 1
            reasons.append("ema_downtrend")

        macd_line, signal_line, histogram = macd(
            closes,
            self.config.macd_fast,
            self.config.macd_slow,
            self.config.macd_signal,
        )
        if macd_line < signal_line and histogram < 0:
            score += 1
            reasons.append("macd_negative")

        if rsi(closes, self.config.rsi_period) >= self.config.rsi_overbought:
            score += 1
            reasons.append("rsi_overbought")

        _lower, _middle, upper = bollinger_bands(closes, self.config.bollinger_period)
        if latest_price >= upper:
            score += 1
            reasons.append("bollinger_upper")

        return score, reasons
