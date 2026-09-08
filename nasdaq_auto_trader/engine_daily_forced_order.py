from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from math import isfinite

from .automatic_order_context import automatic_order_context
from .automatic_order_types import AutomaticBlockRequest
from .config_manager import record_submitted_order
from .engine_types import EngineCycleItem, JsonObject
from .market_hours import regular_market_session
from .models import AccountSnapshot, Bar, OrderRequest, Position, TradeDecision
from .automatic_selection import AutomaticSelectionResult


@dataclass(frozen=True, slots=True)
class ForcedCandidate:
    symbol: str
    decision: TradeDecision
    bars: list[Bar]


class EngineDailyForcedOrderMixin:
    def _run_daily_forced_order(
        self,
        selection: AutomaticSelectionResult,
        account: AccountSnapshot,
        positions: dict[str, Position],
    ) -> list[EngineCycleItem] | None:
        now = self._clock()
        if not self._daily_forced_order_due(now):
            return None
        if self.config.mode == "live" and self.config.broker != "kis":
            return [self._unavailable_result(account, "daily_forced_order_kis_required")]
        for candidate in self._forced_buy_candidates(selection, positions):
            result = self._execute_forced_candidate(candidate, account, positions)
            if result is not None:
                return [result]
        return [self._unavailable_result(account, "daily_forced_order_candidate_unavailable")]

    def _daily_forced_order_due(self, now: datetime) -> bool:
        settings = self.trading_settings
        if settings is None or not settings.daily_forced_order_enabled:
            return False
        self.trading_session_state.reset_if_new_day(now)
        if self.trading_session_state.buy_count + self.trading_session_state.sell_count > 0:
            return False
        session = regular_market_session(now)
        if not session.is_open:
            return False
        market_now = datetime.fromisoformat(session.market_time)
        opens_at = datetime.fromisoformat(session.opens_at)
        closes_at = datetime.fromisoformat(session.closes_at)
        starts_at = opens_at + timedelta(minutes=settings.market_open_wait_minutes)
        stops_at = closes_at - timedelta(minutes=settings.market_close_stop_minutes)
        return starts_at <= market_now < stops_at

    def _forced_buy_candidates(
        self,
        selection: AutomaticSelectionResult,
        positions: dict[str, Position],
    ) -> tuple[ForcedCandidate, ...]:
        candidates: list[ForcedCandidate] = []
        ranking = selection.prethreshold_ranked or selection.report.ranked
        for ranked in ranking:
            position = positions.get(ranked.symbol)
            if position is not None and position.qty > 0:
                continue
            bars = selection.bars_by_symbol.get(ranked.symbol, [])
            if not bars or bars[-1].close <= 0:
                continue
            quote = selection.quotes_by_symbol.get(ranked.symbol)
            price = quote[1] if quote is not None else bars[-1].close
            if not isfinite(price) or price <= 0:
                continue
            candidates.append(
                ForcedCandidate(
                    ranked.symbol,
                    TradeDecision(
                        ranked.symbol,
                        "buy",
                        round(ranked.score * 100),
                        price,
                        [*ranked.reasons, "daily_forced_order"],
                    ),
                    bars,
                )
            )
        return tuple(candidates)

    def _execute_forced_candidate(
        self,
        candidate: ForcedCandidate,
        account: AccountSnapshot,
        positions: dict[str, Position],
    ) -> EngineCycleItem | None:
        order_account, buying_power_check = self._account_for_order(
            account,
            candidate.symbol,
            candidate.decision.latest_price,
        )
        order = OrderRequest(
            symbol=candidate.symbol,
            side="buy",
            type="limit",
            qty=1,
            limit_price=candidate.decision.latest_price,
        )
        if not all(
            isfinite(value)
            for value in (
                candidate.decision.latest_price,
                order_account.cash,
                order_account.buying_power,
            )
        ):
            return None
        if order.side == "buy" and (
            order_account.cash < candidate.decision.latest_price
            or order_account.buying_power < candidate.decision.latest_price
        ):
            return None
        response = self._settings_block_response(order, order_account, None)
        context = automatic_order_context(self, candidate.bars)
        if response is not None and context is not None and self.config.mode == "live":
            self.automatic_order_guard.record_block(
                AutomaticBlockRequest(
                    context,
                    order,
                    str(response.get("reason", "settings_guard_blocked")),
                )
            )
        if response is not None:
            return None
        if context is not None:
            context = replace(
                context,
                max_daily_order_count=1,
                authorization_purpose="daily_forced",
            )
        response = self._submit_or_block_order(order, context)
        record_submitted_order(
            order,
            response,
            self.trading_session_state,
            self._clock(),
        )
        return self._forced_result(
            candidate,
            order,
            response,
            order_account,
            buying_power_check,
        )

    @staticmethod
    def _forced_result(
        candidate: ForcedCandidate,
        order: OrderRequest | None,
        response: JsonObject | None,
        account: AccountSnapshot,
        buying_power_check: JsonObject | None,
    ) -> EngineCycleItem:
        return {
            "symbol": candidate.symbol,
            "decision": candidate.decision,
            "order": order,
            "response": response,
            "account": account,
            "buying_power_check": buying_power_check,
            "trading_agents": None,
            "daily_forced_order": True,
        }

    @staticmethod
    def _unavailable_result(account: AccountSnapshot, reason: str) -> EngineCycleItem:
        return {
            "symbol": "",
            "decision": None,
            "order": None,
            "response": {"status": "blocked", "reason": reason},
            "account": account,
            "buying_power_check": None,
            "trading_agents": None,
            "daily_forced_order": True,
        }
