from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Final, assert_never

from .ai_quant_lab.types import JsonObject
from .automatic_risk import AutomaticRiskLimits, CycleReservationLedger
from .brokers.common import BrokerRequestError
from .config import AppConfig
from .config_manager import (
    TradingSessionState,
    TradingSettings,
    validate_order_against_settings,
)
from .daily_buy_objective import daily_minimum_decision
from .entry_pricing import price_entry_decision
from .models import AccountSnapshot, Bar, Position
from .risk import RiskManager
from .strategy import TechnicalStrategy

_DEFERRED_SETTINGS_BLOCKS: Final = frozenset({
    "sell_only_mode",
    "max_daily_buy_count_reached",
    "max_daily_loss_reached",
    "daily_loss_state_unavailable",
    "cooldown_active",
    "market_open_wait_active",
    "market_close_stop_active",
    "buy_confirmation_required",
})
_DEFERRED_LEARNED_BLOCKS: Final = frozenset({
    "learned_daily_order_limit_reached",
    "learned_daily_loss_state_unavailable",
    "learned_daily_loss_limit_reached",
    "learned_exposure_state_unavailable",
})


@dataclass(frozen=True, slots=True)
class EntryEligibilityResult:
    eligible_symbols: frozenset[str]
    warnings: tuple[str, ...]
    daily_loss_breached: bool


@dataclass(frozen=True, slots=True)
class EntryEligibilityContext:
    account: AccountSnapshot
    positions: Mapping[str, Position]
    settings: TradingSettings | None = None
    session_state: TradingSessionState = field(default_factory=TradingSessionState)
    account_for_order: Callable[
        [AccountSnapshot, str, float], tuple[AccountSnapshot, JsonObject | None]
    ] | None = None
    daily_minimum_due: bool = False
    entry_prices: Mapping[str, float] = field(default_factory=dict)

    def evaluate(
        self,
        config: AppConfig,
        bars_by_symbol: Mapping[str, list[Bar]],
        risk_limits: AutomaticRiskLimits,
        now: datetime,
    ) -> EntryEligibilityResult:
        strategy = TechnicalStrategy(config.strategy)
        risk = RiskManager(config.risk)
        eligible: set[str] = set()
        warnings: list[str] = []
        daily_loss_breached = False
        for symbol, bars in bars_by_symbol.items():
            position = self.positions.get(symbol)
            decision = strategy.decide(symbol, bars, position)
            decision = daily_minimum_decision(
                strategy, decision, bars, position, due=self.daily_minimum_due,
            )
            decision = price_entry_decision(
                decision, self.entry_prices.get(symbol), config.strategy.stop_loss_pct,
            )
            match decision.action:
                case "hold" | "sell":
                    warnings.append(
                        f"entry_technical_{decision.action}:{symbol}:"
                        + ",".join(decision.reasons)
                    )
                case "buy":
                    if risk.build_order(
                        decision, self.account, position, decision.latest_price,
                    ) is None:
                        warnings.append(f"entry_risk_capacity:{symbol}")
                        continue
                    account = self.account
                    if self.account_for_order is not None:
                        try:
                            account, _ = self.account_for_order(
                                account, symbol, decision.latest_price,
                            )
                        except (BrokerRequestError, OSError):
                            warnings.append(f"entry_buying_power_unavailable:{symbol}")
                            continue
                    order = risk.build_order(
                        decision, account, position, decision.latest_price,
                    )
                    if order is None:
                        warnings.append(f"entry_risk_capacity:{symbol}")
                        continue
                    session = replace(self.session_state)
                    session.observe_account(account, now)
                    if self.settings is not None:
                        blocked = validate_order_against_settings(
                            order, account, position, self.settings, session,
                            now, config.mode,
                        )
                        daily_loss_breached |= session.daily_loss_breached
                        if blocked is not None:
                            warnings.append(
                                f"entry_settings:{symbol}:{blocked['reason']}",
                            )
                            if blocked["reason"] in _DEFERRED_SETTINGS_BLOCKS:
                                eligible.add(symbol)
                            continue
                    _, reason = CycleReservationLedger().apply_limits(
                        order, decision, decision.latest_price, self.account,
                        dict(self.positions), risk_limits,
                        session.buy_count + session.sell_count,
                        session.starting_equity,
                        integer_quantity_enabled=config.risk.integer_quantity_enabled,
                        estimated_roundtrip_cost_pct=config.risk.estimated_roundtrip_cost_pct,
                        estimated_roundtrip_minimum_cost_usd=config.risk.estimated_roundtrip_minimum_cost_usd,
                        estimated_sell_tax_pct=config.risk.estimated_sell_tax_pct,
                    )
                    if reason:
                        warnings.append(f"entry_learned_risk:{symbol}:{reason}")
                        if reason in _DEFERRED_LEARNED_BLOCKS:
                            eligible.add(symbol)
                        continue
                    eligible.add(symbol)
                case unreachable:
                    assert_never(unreachable)
        return EntryEligibilityResult(
            frozenset(eligible), tuple(warnings), daily_loss_breached,
        )
