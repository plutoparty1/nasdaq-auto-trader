from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from nasdaq_auto_trader.ai_quant_lab.strategy_schema import (
    SignalSpec,
    SignalType,
    StrategySpec,
)
from nasdaq_auto_trader.quant_data.features import FeatureRow
from nasdaq_auto_trader.strategies.base_strategy import SignalDecision, TargetPosition


@dataclass(frozen=True, slots=True)
class WhitelistedStrategy:
    spec: StrategySpec

    def validate_spec(self) -> bool:
        return bool(self.spec.research_basis.source_ids and self.spec.signals)

    def required_features(self) -> tuple[str, ...]:
        features: set[str] = set()
        for signal in self.spec.signals:
            features.update(_required_features_for_signal(signal.signal_type))
        return tuple(sorted(features))

    def generate_signals(
        self,
        features_by_symbol: dict[str, FeatureRow],
    ) -> tuple[SignalDecision, ...]:
        signals = [
            self._signal_for_symbol(symbol, row)
            for symbol, row in features_by_symbol.items()
        ]
        return tuple(signal for signal in signals if signal.score >= 0)

    def rank_and_select(
        self,
        signals: tuple[SignalDecision, ...],
    ) -> tuple[SignalDecision, ...]:
        selected = [
            signal
            for signal in signals
            if signal.score >= self.spec.entry_rule.threshold
        ]
        ranked = sorted(selected, key=lambda signal: (-signal.score, signal.symbol))
        return tuple(ranked[: self.spec.entry_rule.top_n])

    def generate_target_positions(
        self,
        signals: tuple[SignalDecision, ...],
    ) -> tuple[TargetPosition, ...]:
        return tuple(
            TargetPosition(
                symbol=signal.symbol,
                side="buy",
                confidence=signal.confidence,
                position_strength=signal.position_strength,
                entry_price=signal.entry_price,
                stop_price=signal.stop_price,
                strategy_id=self.spec.strategy_id,
            )
            for signal in signals
        )

    def explain_decision(self, signal: SignalDecision) -> str:
        return "; ".join(signal.reasons)

    def _signal_for_symbol(self, symbol: str, row: FeatureRow) -> SignalDecision:
        contributions = [
            _score_signal(signal, row) * signal.weight for signal in self.spec.signals
        ]
        score = max(min(sum(contributions), 1.0), 0.0)
        atr_stop = row.atr_14 * self.spec.exit_rule.stop_loss_atr_multiple
        stop_price = max(row.current_price - atr_stop, 0.0)
        return SignalDecision(
            symbol=symbol,
            score=score,
            confidence=score,
            position_strength=score,
            entry_price=row.current_price,
            stop_price=stop_price,
            reasons=tuple(_reason_for_signal(signal, row) for signal in self.spec.signals),
        )


def build_strategy(spec: StrategySpec) -> WhitelistedStrategy:
    return WhitelistedStrategy(spec)


def _required_features_for_signal(signal_type: SignalType) -> tuple[str, ...]:
    lookup = {
        SignalType.TREND_FOLLOWING: ("sma_20", "sma_60", "time_series_momentum"),
        SignalType.CROSS_SECTIONAL_MOMENTUM: ("cross_sectional_rank",),
        SignalType.TIME_SERIES_MOMENTUM: ("time_series_momentum",),
        SignalType.MEAN_REVERSION: ("zscore_20", "short_term_reversal"),
        SignalType.BOLLINGER_ZSCORE: ("bollinger_position", "zscore_20"),
        SignalType.RSI_OSCILLATOR: ("rsi_14",),
        SignalType.VOLATILITY_BREAKOUT: ("atr_14", "volatility_20d"),
        SignalType.BREAKOUT: ("rolling_return_20d", "atr_14"),
        SignalType.PAIR_TRADING_STAT_ARB: ("zscore_20", "beta_to_qqq"),
        SignalType.FACTOR_STRATEGY: ("momentum_factor", "low_volatility_factor", "liquidity_factor"),
        SignalType.SECTOR_THEME_ROTATION: ("relative_strength_20d",),
        SignalType.VOLATILITY_TARGETING: ("volatility_20d", "atr_14"),
        SignalType.VOLATILITY_FILTER: ("volatility_20d", "atr_14"),
    }
    return lookup[signal_type]


def _score_signal(signal: SignalSpec, row: FeatureRow) -> float:
    match signal.signal_type:
        case SignalType.TREND_FOLLOWING:
            return _positive(row.sma_20 - row.sma_60) * 0.5 + _positive(row.time_series_momentum) * 0.5
        case SignalType.CROSS_SECTIONAL_MOMENTUM:
            return row.cross_sectional_rank
        case SignalType.TIME_SERIES_MOMENTUM:
            return _positive(row.time_series_momentum)
        case SignalType.MEAN_REVERSION:
            return _bounded(-row.zscore_20 / 2) if row.zscore_20 < 0 else 0.0
        case SignalType.BOLLINGER_ZSCORE:
            return _bounded(1 - row.bollinger_position) if row.bollinger_position < 0.5 else 0.0
        case SignalType.RSI_OSCILLATOR:
            return _bounded((50 - row.rsi_14) / 20) if row.rsi_14 < 50 else 0.0
        case SignalType.VOLATILITY_BREAKOUT:
            return _bounded(row.atr_14 / row.dollar_volume) if row.dollar_volume > 0 else 0.0
        case SignalType.BREAKOUT:
            return _positive(row.rolling_return_20d)
        case SignalType.PAIR_TRADING_STAT_ARB:
            return _bounded(abs(row.zscore_20) / 3)
        case SignalType.FACTOR_STRATEGY:
            return _bounded(row.momentum_factor + row.low_volatility_factor * 0.1)
        case SignalType.SECTOR_THEME_ROTATION:
            return _positive(row.relative_strength_20d)
        case SignalType.VOLATILITY_TARGETING:
            return _bounded(1 / (1 + row.volatility_20d))
        case SignalType.VOLATILITY_FILTER:
            return _bounded(1 / (1 + row.volatility_20d))
        case unreachable:
            assert_never(unreachable)


def _reason_for_signal(signal: SignalSpec, row: FeatureRow) -> str:
    return f"{signal.signal_type.value}:{_score_signal(signal, row):.3f}"


def _positive(value: float) -> float:
    return _bounded(value * 10)


def _bounded(value: float) -> float:
    return max(min(value, 1.0), 0.0)
