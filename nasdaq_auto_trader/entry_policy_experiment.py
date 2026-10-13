from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime
from math import isfinite
from typing import assert_never

from .entry_policy_experiment_models import (
    EntryDecisionRecord,
    EntryPolicyInputError,
    EntryPolicyName,
    completed_timestamp,
    market_session,
    parse_policy,
)
from .models import Bar, Position, TradeDecision
from .strategy import TechnicalStrategy
from .strategy_config import StrategyConfig


class EntryPolicyStrategy(TechnicalStrategy):
    """Offline mutable signal/fill ledger; production engine never selects this class."""

    def __init__(self, config: StrategyConfig, policy: str) -> None:
        super().__init__(config)
        self.policy: EntryPolicyName = parse_policy(policy)
        self.records: list[EntryDecisionRecord] = []
        self._completed: dict[str, datetime] = {}
        self._filled_qty: dict[str, float] = {}
        self._session_qty: dict[str, float] = {}
        self._accepted_timestamp: str = ""
        self._risk_distance: dict[str, float] = {}

    @property
    def filled_buy_sessions(self) -> frozenset[str]:
        return frozenset(key for key, qty in self._session_qty.items() if qty >= 1)

    def decide(self, symbol: str, bars: list[Bar], position: Position | None) -> TradeDecision:
        return self.evaluate(symbol, bars, position,
                             evaluation_timestamp=bars[-1].timestamp if bars else "")

    def evaluate(
        self, symbol: str, bars: list[Bar], position: Position | None, *,
        evaluation_timestamp: str, completed_bar_id: str | None = None,
    ) -> TradeDecision:
        identity = completed_bar_id or (bars[-1].timestamp if bars else "")
        completion = completed_timestamp(identity)
        observed = completed_timestamp(evaluation_timestamp)
        incomplete = bool(completion is None or observed is None or completion > observed)
        previous = self._completed.get(symbol)
        duplicate = bool(completion is not None and previous is not None and completion <= previous)
        if completion is not None and not incomplete and not duplicate:
            self._completed[symbol] = completion
        protection_bars = bars if not incomplete else self._completed_protection_bars(symbol, bars, position, observed)
        protective = self.protective_exit(symbol, protection_bars, position)
        base = protective or (TradeDecision(symbol, "hold", 0, 0, ["completed_bar_unavailable_or_future"])
                              if incomplete else super().decide(symbol, bars, position))
        buy_score, sell_score = (None, None) if incomplete else self._same_data_scores(bars)
        decision = base
        if protective is None and not incomplete:
            decision = self._entry_policy(base, bars, position, evaluation_timestamp,
                                          duplicate, sell_score)
        forced = decision.action == "buy" and base.action != "buy"
        if decision.action == "buy" and decision.risk_per_share is not None:
            self._risk_distance[symbol] = decision.risk_per_share
        indicator_price = bars[-1].close if bars else None
        mark = position.market_value / position.qty if position is not None and position.qty > 0 else None
        self.records.append(EntryDecisionRecord(
            symbol=symbol, policy=self.policy, evaluation_timestamp=evaluation_timestamp,
            completed_bar_id=identity,
            data_fingerprint=hashlib.sha256(json.dumps([asdict(bar) for bar in bars],
                                                     sort_keys=True).encode()).hexdigest(),
            buy_score=buy_score, sell_score=sell_score,
            base_action=base.action, final_action=decision.action, forced=forced,
            no_trade=decision.action == "hold", reason=decision.reasons[-1] if decision.reasons else "no_signal",
            entry_condition_met=buy_score is not None and buy_score >= self.config.buy_score,
            duplicate_general_evaluation=duplicate, protective_evaluation=protective is not None,
            indicator_price=indicator_price, protective_mark=mark,
            stress_risk_distance=decision.risk_per_share,
        ))
        return decision

    def _completed_protection_bars(
        self, symbol: str, bars: list[Bar], position: Position | None,
        observed: datetime | None,
    ) -> list[Bar]:
        completed = [bar for bar in bars
                     if (timestamp := completed_timestamp(bar.timestamp)) is not None
                     and observed is not None and timestamp <= observed]
        if completed or position is None or position.qty <= 0:
            return completed
        mark = position.market_value / position.qty
        if not isfinite(mark) or mark <= 0:
            return []
        return [Bar(symbol, observed.isoformat() if observed else "", mark, mark, mark, mark, 0)]

    def _entry_policy(
        self, base: TradeDecision, bars: list[Bar], position: Position | None,
        timestamp: str, duplicate: bool, sell_score: int | None,
    ) -> TradeDecision:
        match self.policy:
            case "A":
                due = market_session(timestamp) not in self.filled_buy_sessions
                return self._minimum_proxy(base, bars, position,
                                           due=due and timestamp != self._accepted_timestamp)
            case "B":
                return base
            case "C":
                if duplicate:
                    return replace(base, action="hold", reasons=[*base.reasons, "completed_bar_already_evaluated"])
                if position is None and base.action == "buy" and sell_score is not None and sell_score >= self.config.sell_score:
                    return replace(base, action="hold", reasons=[*base.reasons, "conflicting_entry_exit_signal"])
                return base
            case unreachable:
                assert_never(unreachable)

    def _minimum_proxy(self, decision: TradeDecision, bars: list[Bar],
                       position: Position | None, *, due: bool) -> TradeDecision:
        if (not due or decision.action != "hold" or position is not None
                or len(bars) < self._minimum_bars()
                or not isfinite(decision.latest_price) or decision.latest_price <= 0):
            return decision
        distance = decision.risk_per_share
        if distance is None:
            distance = self._risk_per_share(bars, decision.latest_price)
        if distance is None or not isfinite(distance) or distance <= 0:
            return decision
        return replace(decision, action="buy", risk_per_share=distance,
                       reasons=[*decision.reasons, "daily_minimum_best_affordable"])

    def _same_data_scores(self, bars: list[Bar]) -> tuple[int | None, int | None]:
        if len(bars) < self._minimum_bars():
            return None, None
        closes = [bar.close for bar in bars]
        if not all(isfinite(value) and value > 0 for value in closes):
            return None, None
        return (self._buy_score(closes, bars, closes[-1])[0],
                self._sell_score(closes, bars, closes[-1])[0])

    def register_order_accepted(self, symbol: str, evaluation_timestamp: str) -> None:
        del symbol
        self._accepted_timestamp = evaluation_timestamp

    def initial_stop_for(self, symbol: str, fill_price: float) -> float | None:
        """Return the shared conservative sizing floor, not the first triggering legacy stop."""
        distance = self._risk_distance.get(symbol)
        if distance is None or not isfinite(distance) or distance <= 0:
            return None
        floor = fill_price - max(distance, fill_price * self.config.stop_loss_pct)
        return floor if isfinite(floor) and 0 < floor < fill_price else None

    def register_entry_fill(self, symbol: str, price: float, qty: float, timestamp: str) -> None:
        if not all(isfinite(value) and value > 0 for value in (price, qty)):
            raise EntryPolicyInputError("entry fill price and quantity must be positive finite values")
        added = qty - self._filled_qty.get(symbol, 0)
        if added > 0:
            session = market_session(timestamp)
            self._session_qty[session] = self._session_qty.get(session, 0) + added
        self._filled_qty[symbol] = qty

    def register_exit_fill(self, symbol: str, remaining_qty: float) -> None:
        if not isfinite(remaining_qty) or remaining_qty < 0:
            raise EntryPolicyInputError("remaining quantity must be nonnegative and finite")
        self._filled_qty[symbol] = remaining_qty
