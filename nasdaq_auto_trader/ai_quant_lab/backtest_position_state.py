from __future__ import annotations

from dataclasses import dataclass

from .strategy_schema import ExitRule


@dataclass(frozen=True, slots=True)
class OpenPosition:
    entry_price: float
    entry_index: int
    peak_price: float
    risk_distance: float

    def observe(self, price: float) -> OpenPosition:
        return OpenPosition(
            self.entry_price,
            self.entry_index,
            max(self.peak_price, price),
            self.risk_distance,
        )

    def should_exit(self, price: float, index: int, rule: ExitRule) -> bool:
        held_too_long = index - self.entry_index >= rule.max_holding_days
        stop_hit = price <= self.entry_price - self.risk_distance
        atr_distance = self.risk_distance / rule.stop_loss_atr_multiple
        take_profit_hit = (
            price >= self.entry_price + (atr_distance * rule.take_profit_atr_multiple)
        )
        trailing_hit = (
            rule.trailing_stop and price <= self.peak_price - self.risk_distance
        )
        return held_too_long or stop_hit or take_profit_hit or trailing_hit
