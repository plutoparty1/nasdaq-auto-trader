from __future__ import annotations

from dataclasses import replace

from .automatic_order_guard import (
    AutomaticOrderBlock,
    AutomaticOrderContext,
)
from .automatic_order_types import AutomaticBlockRequest
from .broker_response import broker_response_status, broker_response_submitted
from .config_manager import TradingSessionState, TradingSettings, validate_order_against_settings
from .engine_types import BrokerResponsePayload, JsonObject
from .market_hours import regular_market_session
from .models import AccountSnapshot, OrderRequest, Position, TradeDecision


class EngineOrderMixin:
    def _submit_or_block_order(
        self,
        order: OrderRequest,
        automatic_context: AutomaticOrderContext | None = None,
    ) -> BrokerResponsePayload:
        """Submit an order only when the configured session gate permits it."""

        automatic_live = bool(
            self.config.mode == "live"
            and self.trading_settings is not None
            and self.trading_settings.auto_symbol_selection_enabled
        )
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
            final_block = self.automatic_order_guard.confirm(
                permit,
                order,
                self._clock(),
            )
            if final_block is not None:
                return {
                    "status": "blocked",
                    "reason": final_block.reason,
                    "terminal": final_block.terminal,
                }
        response = self.broker.submit_order(order)
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
        if response_status == "order_response_missing_status":
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
