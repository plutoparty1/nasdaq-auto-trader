from __future__ import annotations

from dataclasses import replace
from math import isfinite

from .entry_policy_experiment import EntryPolicyStrategy
from .entry_policy_experiment_models import completed_timestamp
from .experimental_exit import ExperimentalExitStrategy
from .experimental_exit_models import EntryVolatility, ExitPolicy
from .experimental_exit_state import valid_atr
from .models import Bar, Position, TradeDecision
from .strategy_config import StrategyConfig


class ProfitabilityStrategy(EntryPolicyStrategy):
    """Offline C entry gates with retained candidate exit state and entry ATR."""

    def __init__(self, config: StrategyConfig, policy: ExitPolicy | None) -> None:
        super().__init__(config, "C")
        self.exit_strategy: ExperimentalExitStrategy | None = (
            None if policy is None else ExperimentalExitStrategy(config, policy)
        )
        self.entry_volatility: dict[str, float | None] = {}
        self.filled_stops: dict[str, float] = {}

    def evaluate(
        self, symbol: str, bars: list[Bar], position: Position | None, *,
        evaluation_timestamp: str, completed_bar_id: str | None = None,
    ) -> TradeDecision:
        if position is None:
            _ = self.filled_stops.pop(symbol, None)
            observed = completed_timestamp(evaluation_timestamp)
            completed = [bar for bar in bars
                         if (stamp := completed_timestamp(bar.timestamp)) is not None
                         and observed is not None and stamp <= observed]
            period = (self.config.atr_period if self.exit_strategy is None
                      else self.exit_strategy.policy.atr_period)
            volatility = valid_atr(completed, period)
            self.entry_volatility[symbol] = volatility
            if self.exit_strategy is not None:
                _ = self.exit_strategy.state.positions.pop(symbol, None)
                self.exit_strategy.state.pending[symbol] = EntryVolatility(
                    volatility, completed[-1].timestamp if completed else "",
                )
        return super().evaluate(symbol, bars, position,
                                evaluation_timestamp=evaluation_timestamp,
                                completed_bar_id=completed_bar_id)

    def _entry_policy(
        self, base: TradeDecision, bars: list[Bar], position: Position | None,
        timestamp: str, duplicate: bool, sell_score: int | None,
    ) -> TradeDecision:
        decision = super()._entry_policy(base, bars, position, timestamp, duplicate, sell_score)
        if decision.action == "buy" and self.initial_stop_for(decision.symbol, decision.latest_price) is None:
            reason = ("invalid_entry_atr" if self.entry_volatility.get(decision.symbol) is None
                      else "entry_stop_outside_bounds")
            return replace(decision, action="hold", reasons=[reason], risk_per_share=None)
        return decision

    def _risk_per_share(self, bars: list[Bar], latest_price: float) -> float | None:
        if self.exit_strategy is not None:
            stop = self.exit_strategy.initial_stop_for(bars[-1].symbol, latest_price)
            return None if stop is None else latest_price - stop
        fixed = latest_price * self.config.stop_loss_pct
        volatility = valid_atr(bars, self.config.atr_period)
        return fixed if volatility is None else min(fixed, volatility * self.config.atr_stop_multiplier)

    def initial_stop_for(self, symbol: str, fill_price: float) -> float | None:
        if not isfinite(fill_price) or fill_price <= 0:
            return None
        if self.exit_strategy is not None:
            return self.exit_strategy.initial_stop_for(symbol, fill_price)
        if symbol in self.filled_stops:
            return self.filled_stops[symbol]
        volatility = self.entry_volatility.get(symbol)
        fixed = fill_price * self.config.stop_loss_pct
        distance = fixed if volatility is None else min(fixed, volatility * self.config.atr_stop_multiplier)
        stop = fill_price - distance
        return stop if 0 < stop < fill_price else None

    def _position_guard(self, symbol: str, bars: list[Bar], position: Position) -> TradeDecision | None:
        if self.exit_strategy is not None:
            return self.exit_strategy.protective_exit(symbol, bars, position)
        return super()._position_guard(symbol, bars, position)

    def register_entry_fill(self, symbol: str, price: float, qty: float, timestamp: str) -> None:
        stop = self.initial_stop_for(symbol, price)
        super().register_entry_fill(symbol, price, qty, timestamp)
        if stop is not None:
            self.filled_stops[symbol] = stop
        if self.exit_strategy is not None:
            self.exit_strategy.register_entry_fill(symbol, price, qty, timestamp)

    def register_exit_fill(self, symbol: str, remaining_qty: float) -> None:
        super().register_exit_fill(symbol, remaining_qty)
        if self.exit_strategy is not None:
            self.exit_strategy.register_exit_fill(symbol, remaining_qty)
        if remaining_qty == 0:
            _ = self.filled_stops.pop(symbol, None)
            _ = self.entry_volatility.pop(symbol, None)
