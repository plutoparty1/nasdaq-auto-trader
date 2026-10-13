from __future__ import annotations

from dataclasses import replace

from .automatic_buy_receipts import OrderHistorySource
from .automatic_order_guard import (
    AutomaticOrderBlock,
    AutomaticOrderContext,
)
from .automatic_order_pending import automatic_pending_order_block
from .automatic_order_types import AutomaticBlockRequest
from .broker_response import (
    broker_response_reconcile_required,
    broker_response_status,
    broker_response_submitted,
)
from .brokers.common import BrokerOrderRejected, BrokerRequestError
from .config_manager import (
    validate_order_against_settings,
)
from .daily_buy_objective import daily_buy_due
from .engine_types import BrokerResponsePayload, JsonObject
from .market_hours import EASTERN, regular_market_session
from .models import AccountSnapshot, OrderRequest, Position, TradeDecision
from .production_policy import production_order_block
from .safe_runtime import orders_locked


class EngineOrderMixin:
    def _submit_or_block_order(
        self,
        order: OrderRequest,
        automatic_context: AutomaticOrderContext | None = None,
        latest_price: float = 0.0,
        *,
        daily_minimum_buy: bool = False,
        risk_per_share: float | None = None,
    ) -> BrokerResponsePayload:
        """Submit an order only when the configured session gate permits it."""

        if orders_locked():
            return {"status": "blocked", "reason": "safe_release_order_lock", "submitted_order": False}
        production_reason = production_order_block(
            self, order, self._clock(),
        )
        if production_reason:
            return {"status": "blocked", "reason": production_reason, "submitted_order": False}
        automatic_live = bool(
            self.config.mode == "live"
            and self.trading_settings is not None
            and self.trading_settings.auto_symbol_selection_enabled
        )
        unattended_live_without_strategy = bool(
            self.config.mode == "live"
            and order.side == "buy"
            and self.trading_settings is not None
            and self.trading_settings.unattended_operation_enabled
            and not self.trading_settings.auto_symbol_selection_enabled
        )
        if unattended_live_without_strategy:
            return {
                "status": "blocked",
                "reason": "unattended_live_requires_approved_strategy",
                "terminal": True,
            }
        if automatic_live and automatic_context is None:
            return {
                "status": "blocked",
                "reason": "automatic_order_context_missing",
                "terminal": True,
            }
        if self.config.mode == "live":
            if not self.config.allow_live_trading:
                if automatic_context is not None:
                    self.automatic_order_guard.record_block(
                        AutomaticBlockRequest(
                            automatic_context,
                            order,
                            "live_trading_disabled",
                        )
                    )
                return {"status": "blocked", "reason": "live_trading_disabled"}
            if not self.live_order_confirmation:
                if automatic_context is not None:
                    self.automatic_order_guard.record_block(
                        AutomaticBlockRequest(
                            automatic_context,
                            order,
                            "live_order_confirmation_required",
                        )
                    )
                return {
                    "status": "blocked",
                    "reason": "live_order_confirmation_required",
                }
        if self.config.mode == "dry_run":
            return {
                "status": "dry_run",
                "reason": "dry_run",
                "submitted_order": False,
            }
        if self.config.mode != "dry_run" and self.config.regular_market_hours_only:
            session = regular_market_session(self._clock())
            if not session.is_open:
                if automatic_context is not None and self.config.mode == "live":
                    self.automatic_order_guard.record_block(
                        AutomaticBlockRequest(
                            automatic_context,
                            order,
                            "regular_market_closed",
                        )
                    )
                return {
                    "status": "blocked",
                    "reason": "regular_market_closed",
                    "session": session.to_dict(),
                }
        permit = None
        if automatic_context is not None and self.config.mode == "live":
            permit = self.automatic_order_guard.begin(
                automatic_context,
                order,
                self._clock(),
            )
            if isinstance(permit, AutomaticOrderBlock):
                return {
                    "status": "blocked",
                    "reason": permit.reason,
                    "terminal": permit.terminal,
                }
            pending_block = automatic_pending_order_block(
                self, order, latest_price, risk_per_share=risk_per_share,
            )
            if isinstance(pending_block, AutomaticOrderBlock):
                outcome_block = self.automatic_order_guard.finish(
                    permit, {"status": "blocked", "reason": pending_block.reason},
                )
                block = outcome_block or pending_block
                return {"status": "blocked", "reason": block.reason, "terminal": block.terminal}
            permit = replace(permit, initial_position_qty=pending_block.initial_position_qty)
        if daily_minimum_buy:
            now = self._clock()
            history = None
            if isinstance(self.broker, OrderHistorySource):
                market_date = now.astimezone(EASTERN).strftime("%Y%m%d")
                try:
                    history = self.broker.list_order_history(market_date, market_date)
                except (BrokerRequestError, OSError):
                    history = None
            objective = daily_buy_due(
                self.trading_settings, self.trading_session_state, self._clock(), history,
            )
            reason = "" if objective.due else (
                "daily_minimum_objective_changed"
                if objective.reason == "daily_minimum_buy_filled" else objective.reason
            )
            if (order.side != "buy" or order.qty != 1 or order.notional is not None
                or self.trading_settings is None or self.trading_settings.dry_run):
                reason = "daily_minimum_settings_invalid"
            if (self.config.regular_market_hours_only
                and not regular_market_session(self._clock()).is_open):
                reason = "regular_market_closed"
            if reason:
                block = AutomaticOrderBlock(reason)
                if permit is not None:
                    outcome_block = self.automatic_order_guard.finish(
                        permit, {"status": "blocked", "reason": reason},
                    )
                    block = outcome_block or block
                return {"status": "blocked", "reason": block.reason, "terminal": block.terminal}
        if permit is not None:
            final_block = self.automatic_order_guard.confirm(permit, order, self._clock())
            if final_block is not None:
                return {
                    "status": "blocked", "reason": final_block.reason,
                    "terminal": final_block.terminal,
                }
        production_reason = production_order_block(
            self, order, self._clock(),
        )
        if production_reason:
            if permit is not None:
                self.automatic_order_guard.finish(
                    permit, {"status": "blocked", "reason": production_reason},
                )
            return {"status": "blocked", "reason": production_reason, "submitted_order": False}
        try:
            response = self.broker.submit_order(order)
        except BrokerOrderRejected as exc:
            response = {"status": "rejected", "msg_cd": exc.code}
        if permit is not None:
            outcome_block = self.automatic_order_guard.finish(permit, response)
            if outcome_block is not None:
                return {
                    "status": "blocked",
                    "reason": outcome_block.reason,
                    "terminal": outcome_block.terminal,
                    "broker_submitted": broker_response_submitted(response),
                }
        if self.config.mode == "dry_run" or broker_response_submitted(response):
            return response
        response_status = broker_response_status(response)
        if broker_response_reconcile_required(response):
            return {
                "status": "blocked",
                "reason": "order_response_reconcile_required",
                "terminal": True,
                "broker_response": response,
            }
        return {
            "status": "blocked",
            "reason": f"order_response_not_submitted:{response_status}",
            "broker_response": response,
        }

    def _settings_block_response(
        self,
        order: OrderRequest,
        account: AccountSnapshot,
        position: Position | None,
    ) -> JsonObject | None:
        """Apply GUI settings as a final pre-submit safety gate."""

        if self.trading_settings is None:
            return None
        return validate_order_against_settings(
            order,
            account,
            position,
            self.trading_settings,
            self.trading_session_state,
            self._clock(),
            self.config.mode,
        )

    def _time_based_sell_decision(
        self,
        symbol: str,
        decision: TradeDecision,
        position: Position | None,
    ) -> TradeDecision:
        """Turn a hold decision into sell when the GUI session hold timer expires."""

        settings = self.trading_settings
        if (
            settings is None
            or not settings.time_based_sell_enabled
            or position is None
            or position.qty <= 0
            or decision.action == "sell"
        ):
            return decision
        held_minutes = self.trading_session_state.held_minutes(symbol, self._clock())
        if held_minutes is None or held_minutes < settings.max_holding_minutes:
            return decision
        return TradeDecision(
            symbol,
            "sell",
            max(decision.score, 91),
            decision.latest_price,
            [*decision.reasons, "max_holding_minutes"],
            decision.risk_per_share,
        )
