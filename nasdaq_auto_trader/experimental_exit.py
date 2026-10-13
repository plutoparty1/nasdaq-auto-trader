from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from math import isfinite

from .experimental_exit_diagnostics import snapshot
from .experimental_exit_models import (
    EntryVolatility,
    ExitDiagnostics,
    ExitPolicy,
    ExitPolicyError,
    ExitPositionState,
)
from .experimental_exit_state import (
    ExitStateStore,
    effective_stop,
    initial_stop,
    retained_stop,
    valid_atr,
)
from .models import Bar, Position, TradeDecision
from .strategy import TechnicalStrategy
from .strategy_config import StrategyConfig


class ExperimentalExitStrategy(TechnicalStrategy):
    """Offline policy; callers must supply completed bars and acknowledge actual fills."""

    def __init__(self, config: StrategyConfig, policy: ExitPolicy) -> None:
        super().__init__(replace(config, corrected_exits=True))
        self.policy = policy
        fingerprint = hashlib.sha256(json.dumps({"config": asdict(self.config), "policy": asdict(policy)},
                                                sort_keys=True).encode()).hexdigest()[:16]
        self.state = ExitStateStore(fingerprint)
        self.diagnostics: dict[str, ExitDiagnostics] = {}

    def decide(self, symbol: str, bars: list[Bar], position: Position | None) -> TradeDecision:
        if position is not None and position.qty <= 0:
            position = None
        if position is None:
            self.state.positions.pop(symbol, None)
            self.state.pending.pop(symbol, None)
        if not bars:
            return TradeDecision(symbol, "hold", 0, 0, ["no_data"])
        price = bars[-1].close
        if position is not None:
            protected = self._position_guard(symbol, bars, position)
            if protected is not None:
                return protected
        else:
            self.diagnostics[symbol] = snapshot(self.policy, self.config, self.state, symbol, bars, None)
        if not isfinite(price) or price <= 0:
            return TradeDecision(symbol, "hold", 0, 0, ["invalid_price"])
        if len(bars) < self._minimum_bars():
            return TradeDecision(symbol, "hold", 0, price, ["not_enough_data"])
        closes = [bar.close for bar in bars]
        buy_score, buy_reasons = self._buy_score(closes, bars, price)
        sell_score, sell_reasons = self._sell_score(closes, bars, price)
        self.diagnostics[symbol] = replace(self.diagnostics[symbol], buy_score=buy_score, sell_score=sell_score)
        if position is None and buy_score >= self.config.buy_score:
            if self.policy.block_conflicting_entry and sell_score >= self.config.sell_score:
                return TradeDecision(symbol, "hold", buy_score, price, ["conflicting_entry_exit_signal"])
            volatility = valid_atr(bars, self.config.atr_period if self.policy.stop_mode == "legacy" else self.policy.atr_period)
            risk = self._risk_per_share(bars, price)
            if risk is None or risk <= 0:
                reason = "invalid_entry_atr" if volatility is None else "entry_stop_outside_bounds"
                return TradeDecision(symbol, "hold", buy_score, price, [reason])
            self.state.pending[symbol] = EntryVolatility(volatility, bars[-1].timestamp)
            return TradeDecision(symbol, "buy", buy_score, price, buy_reasons, risk)
        if position is not None:
            reason = self._general_gate(symbol, bars[-1].timestamp)
            if reason is not None:
                return TradeDecision(symbol, "hold", sell_score, price, [reason])
            if sell_score >= self.config.sell_score:
                return TradeDecision(symbol, "sell", sell_score, price, sell_reasons)
        score, reasons = (buy_score, buy_reasons) if position is None else (sell_score, sell_reasons)
        return TradeDecision(symbol, "hold", score, price, reasons or ["no_signal"])

    def _general_gate(self, symbol: str, timestamp: str) -> str | None:
        state = self.state.positions[symbol]
        if self.policy.completed_bar_only_general and timestamp == state.last_general_bar_timestamp:
            return "same_completed_bar"
        self.state.positions[symbol] = replace(state, last_general_bar_timestamp=timestamp)
        if self.policy.minimum_general_hold_minutes > 0:
            try:
                now = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc) if "T" not in timestamp else datetime.fromisoformat(timestamp)
                entered = datetime.fromisoformat(state.entry_timestamp)
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
                if entered.tzinfo is None:
                    entered = entered.replace(tzinfo=timezone.utc)
                if (now - entered).total_seconds() < self.policy.minimum_general_hold_minutes * 60:
                    return "minimum_general_hold"
            except ValueError:
                return "unknown_holding_time"
        return None

    def initial_stop_for(self, symbol: str, fill_price: float) -> float | None:
        if not isfinite(fill_price) or fill_price <= 0:
            return None
        previous = self.state.positions.get(symbol)
        if previous is not None:
            return None if previous.initial_stop_price is None else retained_stop(previous)
        pending = self.state.pending.get(symbol)
        stop = initial_stop(self.policy, self.config, fill_price, pending.atr if pending else None)
        return None if stop is None else effective_stop(self.policy, fill_price, stop)

    def register_entry_fill(self, symbol: str, price: float, qty: float, timestamp: str) -> None:
        """Receive the resulting position average and total quantity, never the fill delta."""
        if not all(isfinite(value) and value > 0 for value in (price, qty)):
            raise ExitPolicyError("entry fill average and resulting quantity must be positive")
        previous = self.state.positions.get(symbol)
        if previous is not None:
            self.state.positions[symbol] = replace(previous, entry_price=price, qty=qty)
            return
        pending = self.state.pending.pop(symbol, EntryVolatility(None, timestamp))
        stop = initial_stop(self.policy, self.config, price, pending.atr)
        emergency = None if self.policy.emergency_stop_pct is None else price * (1 - self.policy.emergency_stop_pct)
        self.state.positions[symbol] = ExitPositionState(
            symbol, price, qty, pending.atr, stop, price, False,
            timestamp, pending.bar_timestamp, pending.bar_timestamp, emergency,
        )

    def register_exit_fill(self, symbol: str, remaining_qty: float) -> None:
        if not isfinite(remaining_qty) or remaining_qty < 0:
            raise ExitPolicyError("remaining position quantity must be finite and nonnegative")
        if remaining_qty == 0:
            self.state.positions.pop(symbol, None)
            self.state.pending.pop(symbol, None)
        elif symbol in self.state.positions:
            self.state.positions[symbol] = replace(self.state.positions[symbol], qty=remaining_qty)

    def export_state(self) -> str:
        return self.state.export_state()

    def load_state(self, payload: str) -> None:
        self.state.load_state(payload)

    def _risk_per_share(self, bars: list[Bar], latest_price: float) -> float | None:
        volatility = valid_atr(bars, self.config.atr_period if self.policy.stop_mode == "legacy" else self.policy.atr_period)
        primary = initial_stop(self.policy, self.config, latest_price, volatility)
        stop = None if primary is None else effective_stop(self.policy, latest_price, primary)
        return None if stop is None else latest_price - stop

    def _position_guard(self, symbol: str, bars: list[Bar], position: Position) -> TradeDecision | None:
        price = bars[-1].close
        if position.qty > 0 and position.market_value > 0:
            price = position.market_value / position.qty
        if not isfinite(price) or price <= 0:
            return TradeDecision(symbol, "hold", 0, 0, ["invalid_price"])
        if not isfinite(position.avg_entry_price) or position.avg_entry_price <= 0:
            return TradeDecision(symbol, "hold", 0, price, ["invalid_entry_price"])
        if symbol not in self.state.positions:
            self.register_entry_fill(symbol, position.avg_entry_price, position.qty, bars[-1].timestamp)
        state = self.state.positions[symbol]
        high = max(state.high_water_price, price)
        state = replace(state, entry_price=position.avg_entry_price, qty=position.qty,
                        high_water_price=high, trailing_active=state.trailing_active or
                        high >= position.avg_entry_price * (1 + self.policy.trailing_activation_pct))
        self.state.positions[symbol] = state
        self.diagnostics[symbol] = snapshot(self.policy, self.config, self.state, symbol, bars, position)
        if self.policy.stop_mode == "legacy":
            return super()._position_guard(symbol, bars, replace(position, high_water_price=high))
        stop = retained_stop(state)
        if stop is not None and price <= stop:
            reason = "fixed_stop_loss" if self.policy.stop_mode == "fixed" else "atr_stop_loss"
            if state.initial_stop_price is None or stop > state.initial_stop_price:
                reason = "emergency_fixed_stop_loss"
            return TradeDecision(symbol, "sell", 99, price, [reason])
        if price >= position.avg_entry_price * (1 + self.policy.fixed_take_profit_pct):
            return TradeDecision(symbol, "sell", 90, price, ["fixed_take_profit"])
        if state.trailing_active and price <= high * (1 - self.policy.trailing_drawdown_pct):
            return TradeDecision(symbol, "sell", 88, price, ["trailing_profit_protection"])
        return None
