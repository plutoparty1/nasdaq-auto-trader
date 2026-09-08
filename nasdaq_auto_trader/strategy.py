"""Rule-based strategy that combines classical quant trading signals."""

from __future__ import annotations

from .indicators import (
    atr,
    average_volume,
    bollinger_bands,
    donchian_channel,
    ema,
    macd,
    rate_of_change,
    rsi,
    sma,
    stochastic_oscillator,
)
from .models import Bar, Position, TradeDecision
from .strategy_config import StrategyConfig


class TechnicalStrategy:
    """Blend trend, momentum, mean-reversion, breakout, and volatility rules."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()

    def decide(
        self,
        symbol: str,
        bars: list[Bar],
        position: Position | None,
    ) -> TradeDecision:
        """Return the next action for one symbol from trailing OHLCV bars."""

        if not bars:
            return TradeDecision(symbol, "hold", 0, 0, ["no_data"])

        closes = [bar.close for bar in bars]
        latest_price = closes[-1]
        if position is not None:
            stop_decision = self._position_guard(symbol, bars, position)
            if stop_decision is not None:
                return stop_decision

        minimum_bars = self._minimum_bars()
        if len(bars) < minimum_bars:
            return TradeDecision(symbol, "hold", 0, latest_price, ["not_enough_data"])

        buy_score, buy_reasons = self._buy_score(closes, bars, latest_price)
        sell_score, sell_reasons = self._sell_score(closes, bars, latest_price)

        if position is None and buy_score >= self.config.buy_score:
            return TradeDecision(
                symbol,
                "buy",
                buy_score,
                latest_price,
                buy_reasons,
                self._risk_per_share(bars, latest_price),
            )

        if position is not None and sell_score >= self.config.sell_score:
            return TradeDecision(symbol, "sell", sell_score, latest_price, sell_reasons)

        reasons = buy_reasons if position is None else sell_reasons
        score = buy_score if position is None else sell_score
        return TradeDecision(symbol, "hold", score, latest_price, reasons or ["no_signal"])

    def _minimum_bars(self) -> int:
        """Return the lookback needed before all enabled signals are valid."""

        lookbacks = [
            self.config.sma_slow,
            self.config.ema_slow,
            self.config.rsi_period + 1,
            self.config.macd_slow + self.config.macd_signal,
            self.config.bollinger_period,
            self.config.momentum_period + 1,
            self.config.donchian_period + 1,
            self.config.stochastic_period,
            self.config.volume_period + 1,
            self.config.atr_period + 1,
        ]
        if self.config.use_regime_filter:
            lookbacks.append(self.config.long_sma)
        return max(lookbacks)

    def protective_exit(
        self,
        symbol: str,
        bars: list[Bar],
        position: Position | None,
    ) -> TradeDecision | None:
        if not bars or position is None:
            return None
        return self._position_guard(symbol, bars, position)

    def _position_guard(
        self,
        symbol: str,
        bars: list[Bar],
        position: Position,
    ) -> TradeDecision | None:
        """Apply hard fixed and ATR-based protective exits first."""

        latest_price = bars[-1].close
        if position.qty > 0 and position.market_value > 0:
            latest_price = position.market_value / position.qty
        entry = position.avg_entry_price
        if latest_price <= entry * (1 - self.config.stop_loss_pct):
            return TradeDecision(symbol, "sell", 99, latest_price, ["fixed_stop_loss"])
        if latest_price >= entry * (1 + self.config.take_profit_pct):
            return TradeDecision(symbol, "sell", 90, latest_price, ["fixed_take_profit"])

        high_water = position.high_water_price
        if (
            self.config.trailing_stop_enabled
            and self.config.trailing_stop_activation_pct > 0
            and self.config.trailing_stop_pct > 0
            and high_water is not None
            and high_water
            >= entry * (1 + self.config.trailing_stop_activation_pct)
            and entry < latest_price <= high_water * (1 - self.config.trailing_stop_pct)
        ):
            return TradeDecision(
                symbol,
                "sell",
                88,
                latest_price,
                ["trailing_profit_protection"],
            )

        if len(bars) >= self.config.atr_period + 1:
            atr_value = atr(bars, self.config.atr_period)
            if latest_price <= entry - atr_value * self.config.atr_stop_multiplier:
                return TradeDecision(symbol, "sell", 98, latest_price, ["atr_stop_loss"])
            if latest_price >= entry + atr_value * self.config.atr_take_profit_multiplier:
                return TradeDecision(symbol, "sell", 89, latest_price, ["atr_take_profit"])
        return None

    def _buy_score(
        self,
        closes: list[float],
        bars: list[Bar],
        latest_price: float,
    ) -> tuple[int, list[str]]:
        """Compute the long-entry score from independent classical signals."""

        score = 0
        reasons: list[str] = []

        if self.config.use_regime_filter:
            long_average = sma(closes, self.config.long_sma)
            if latest_price <= long_average:
                return 0, ["below_long_regime"]
            score += 2
            reasons.append("long_regime_up")

        if self.config.buy_trigger_enabled and len(closes) >= 2:
            prior_close = closes[-2]
            drop_trigger = prior_close * (1 - self.config.buy_drop_rate / 100)
            if latest_price <= drop_trigger:
                score += 2
                reasons.append("drop_trigger")

        if self.config.buy_ma_enabled:
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
        if rsi_value <= self.config.rsi_oversold:
            score += 2
            reasons.append("rsi_oversold")
        if 45 <= rsi_value <= self.config.rsi_overbought:
            score += 1
            reasons.append("rsi_trend")

        lower, _middle, _upper = bollinger_bands(closes, self.config.bollinger_period)
        if latest_price <= lower and rsi_value <= 45:
            score += 2
            reasons.append("bollinger_rsi_reversion")

        if rate_of_change(closes, self.config.momentum_period) > 0:
            score += 1
            reasons.append("momentum_positive")

        _prior_low, prior_high = donchian_channel(
            closes[:-1],
            self.config.donchian_period,
        )
        if latest_price > prior_high:
            score += 2
            reasons.append("donchian_breakout")

        stochastic_value = stochastic_oscillator(bars, self.config.stochastic_period)
        if stochastic_value <= self.config.stochastic_oversold and rsi_value <= 45:
            score += 1
            reasons.append("stochastic_reversion")

        if bars[-1].volume > average_volume(bars[:-1], self.config.volume_period):
            score += 1
            reasons.append("volume_confirmation")

        return score, reasons

    def _sell_score(
        self,
        closes: list[float],
        bars: list[Bar],
        latest_price: float,
    ) -> tuple[int, list[str]]:
        """Compute the exit score from trend failure and overextension signals."""

        score = 0
        reasons: list[str] = []

        if self.config.use_regime_filter:
            long_average = sma(closes, self.config.long_sma)
            if latest_price < long_average:
                score += 2
                reasons.append("below_long_regime")

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

        rsi_value = rsi(closes, self.config.rsi_period)
        if rsi_value >= self.config.rsi_overbought:
            score += 1
            reasons.append("rsi_overbought")

        _lower, _middle, upper = bollinger_bands(closes, self.config.bollinger_period)
        if latest_price >= upper and rsi_value >= self.config.rsi_overbought:
            score += 2
            reasons.append("bollinger_overextension")

        if rate_of_change(closes, self.config.momentum_period) < 0:
            score += 1
            reasons.append("momentum_negative")

        prior_low, _prior_high = donchian_channel(
            closes[:-1],
            self.config.donchian_period,
        )
        if latest_price < prior_low:
            score += 2
            reasons.append("donchian_breakdown")

        stochastic_value = stochastic_oscillator(bars, self.config.stochastic_period)
        if stochastic_value >= self.config.stochastic_overbought:
            score += 1
            reasons.append("stochastic_overbought")

        return score, reasons

    def _risk_per_share(self, bars: list[Bar], latest_price: float) -> float | None:
        """Estimate the dollar risk to the ATR or fixed-percent stop."""

        fixed_risk = latest_price * self.config.stop_loss_pct
        if len(bars) < self.config.atr_period + 1:
            return fixed_risk
        atr_risk = atr(bars, self.config.atr_period) * self.config.atr_stop_multiplier
        return max(fixed_risk, atr_risk)
