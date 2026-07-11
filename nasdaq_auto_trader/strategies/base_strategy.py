from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nasdaq_auto_trader.quant_data.features import FeatureRow


@dataclass(frozen=True, slots=True)
class SignalDecision:
    symbol: str
    score: float
    confidence: float
    position_strength: float
    entry_price: float
    stop_price: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TargetPosition:
    symbol: str
    side: str
    confidence: float
    position_strength: float
    entry_price: float
    stop_price: float
    strategy_id: str


class QuantStrategy(Protocol):
    def validate_spec(self) -> bool: ...

    def required_features(self) -> tuple[str, ...]: ...

    def generate_signals(
        self,
        features_by_symbol: dict[str, FeatureRow],
    ) -> tuple[SignalDecision, ...]: ...

    def rank_and_select(
        self,
        signals: tuple[SignalDecision, ...],
    ) -> tuple[SignalDecision, ...]: ...

    def generate_target_positions(
        self,
        signals: tuple[SignalDecision, ...],
    ) -> tuple[TargetPosition, ...]: ...

    def explain_decision(self, signal: SignalDecision) -> str: ...
