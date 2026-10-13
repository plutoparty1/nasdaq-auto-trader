from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import pairwise
from math import isfinite
from typing import override

from .entry_policy_experiment_models import EntryPolicyInputError, completed_timestamp
from .experimental_exit_models import ExitPolicy
from .models import Bar, Position, TradeDecision
from .profitability_strategy import ProfitabilityStrategy
from .strategy_config import StrategyConfig


@dataclass(frozen=True, slots=True)
class BreakoutEntryRecord:
    symbol: str
    evaluation_timestamp: str
    completed_bar_id: str
    data_valid: bool = False
    reason: str = 'insufficient_breakout_history'
    close: float | None = None
    sma_50: float | None = None
    prior_20_high: float | None = None
    prior_20_average_volume: float | None = None
    current_volume: float | None = None
    close_above_sma: bool = False
    close_above_prior_high: bool = False
    volume_above_prior_average: bool = False
    entry_condition_met: bool = False


class BreakoutEntryStrategy(ProfitabilityStrategy):
    """Offline conjunction entry; mutable evidence shares the existing C exit path."""

    def __init__(self, config: StrategyConfig, policy: ExitPolicy) -> None:
        if config.buy_score <= 0:
            raise EntryPolicyInputError('entry adapter requires a positive buy threshold')
        super().__init__(config, policy)
        self.breakout_records: list[BreakoutEntryRecord] = []

    @override
    def evaluate(
        self, symbol: str, bars: list[Bar], position: Position | None, *,
        evaluation_timestamp: str, completed_bar_id: str | None = None,
    ) -> TradeDecision:
        identity = completed_bar_id or (bars[-1].timestamp if bars else '')
        observation = BreakoutEntryRecord(symbol, evaluation_timestamp, identity)
        self.breakout_records.append(self._observe(bars, observation))
        decision = super().evaluate(
            symbol, bars, position, evaluation_timestamp=evaluation_timestamp,
            completed_bar_id=completed_bar_id,
        )
        self.records[-1] = replace(
            self.records[-1], buy_score=None,
            entry_condition_met=self.breakout_records[-1].entry_condition_met,
        )
        return decision

    @override
    def _minimum_bars(self) -> int:
        return max(50, super()._minimum_bars())

    @override
    def _buy_score(
        self, closes: list[float], bars: list[Bar], latest_price: float,
    ) -> tuple[int, list[str]]:
        """Adapt one boolean entry to the shared engine; no legacy score is evaluated."""
        del closes, bars, latest_price
        observation = self.breakout_records[-1]
        if observation.entry_condition_met:
            return self.config.buy_score, ['daily_sma50_high20_volume20_breakout']
        return 0, [observation.reason]

    def _observe(self, bars: list[Bar], empty: BreakoutEntryRecord) -> BreakoutEntryRecord:
        observed = completed_timestamp(empty.evaluation_timestamp)
        completion = completed_timestamp(empty.completed_bar_id)
        if observed is None or completion is None or completion > observed:
            return replace(empty, reason='completed_bar_unavailable_or_future')
        if len(bars) < 50:
            return empty
        recent = bars[-50:]
        timestamps = [completed_timestamp(bar.timestamp) for bar in recent]
        if any(stamp is None or stamp > observed for stamp in timestamps):
            return replace(empty, reason='invalid_or_future_breakout_history')
        if any(left is not None and right is not None and left >= right
               for left, right in pairwise(timestamps)):
            return replace(empty, reason='unordered_breakout_history')
        if any(not all(isfinite(value) and value > 0
                       for value in (bar.open, bar.high, bar.low, bar.close))
               or not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
               or not isfinite(bar.volume) or bar.volume < 0
               for bar in recent):
            return replace(empty, reason='invalid_breakout_ohlcv')
        close = recent[-1].close
        average = sum(bar.close for bar in recent) / 50
        prior = recent[-21:-1]
        high = max(bar.high for bar in prior)
        volume = sum(bar.volume for bar in prior) / 20
        above_average = close > average
        above_high = close > high
        above_volume = recent[-1].volume > volume
        condition = above_average and above_high and above_volume
        return replace(
            empty, data_valid=True,
            reason='breakout_conditions_met' if condition else 'breakout_conditions_not_met',
            close=close, sma_50=average, prior_20_high=high,
            prior_20_average_volume=volume, current_volume=recent[-1].volume,
            close_above_sma=above_average, close_above_prior_high=above_high,
            volume_above_prior_average=above_volume, entry_condition_met=condition,
        )
