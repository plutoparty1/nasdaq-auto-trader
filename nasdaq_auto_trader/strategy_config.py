from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StrategyConfig:
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
    long_sma: int = 200
    momentum_period: int = 63
    donchian_period: int = 55
    stochastic_period: int = 14
    stochastic_oversold: float = 20
    stochastic_overbought: float = 80
    volume_period: int = 20
    atr_period: int = 14
    atr_stop_multiplier: float = 3.0
    atr_take_profit_multiplier: float = 5.0
    buy_score: int = 5
    sell_score: int = 4
    stop_loss_pct: float = 0.07
    take_profit_pct: float = 0.18
    use_regime_filter: bool = True
    buy_trigger_enabled: bool = False
    buy_drop_rate: float = 0.0
    buy_ma_enabled: bool = True
    trailing_stop_enabled: bool = True
    trailing_stop_activation_pct: float = 0.02
    trailing_stop_pct: float = 0.01
    time_based_sell_enabled: bool = False
    max_holding_minutes: int = 180
