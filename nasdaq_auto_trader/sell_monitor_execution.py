from __future__ import annotations

import time

from .broker_response import broker_response_status, broker_response_submitted
from .market_hours import regular_market_session
from .models import OrderRequest
from .sell_monitor_types import JsonObject, SellMonitorResult, SellSnapshot


class SellMonitorExecutionMixin:
    def _submit_sell(
        self,
        snapshot: SellSnapshot,
        trigger: str,
        market_date: str,
    ) -> SellMonitorResult:
        while self.sell_attempts < self.config.max_retries:
            self.sell_attempts += 1
            try:
                session = regular_market_session(self.clock())
                if not session.is_open:
                    return self._finish("blocked", "market_not_open", market_date)
                refreshed = self._snapshot(session.to_dict())
            except Exception as exc:  # noqa: BROAD_EXCEPT_OK
                self.log.append(
                    {
                        "event": "pre_order_snapshot_error",
                        "market_date": market_date,
                        "symbol": self.config.symbol,
                        "side": "sell",
                        "submitted_order": False,
                        "attempt": self.sell_attempts,
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )
                continue

            position_result = self._handle_no_or_unexpected_position(
                refreshed,
                market_date,
            )
            if position_result is not None:
                return position_result

            fresh_trigger = self._sell_trigger(refreshed)
            if fresh_trigger is None:
                return self._finish("blocked", "sell_trigger_no_longer_active", market_date)
            trigger = fresh_trigger
            if not regular_market_session(self.clock()).is_open:
                return self._finish("blocked", "market_not_open", market_date)

            order = self._build_sell_order(refreshed)
            if (
                self.config.sell_only_when_profit
                and order.limit_price is not None
                and order.limit_price <= refreshed.avg_entry_price
            ):
                return self._finish("blocked", "sell_limit_would_allow_loss", market_date)
            self._assert_sell_order_allowed(order, refreshed)
            event = {
                "event": "sell_order_attempt",
                "market_date": market_date,
                "symbol": self.config.symbol,
                "side": "sell",
                "trigger": trigger,
                "attempt": self.sell_attempts,
                "submitted_order": False,
                "dry_run": self.config.dry_run,
                "order": order.to_alpaca_payload(),
                "snapshot": refreshed.to_dict(),
            }
            if self.config.dry_run:
                self.log.append(event)
                return {
                    "status": "dry_run_submitted",
                    "submitted_order": False,
                    "trigger": trigger,
                    "attempts": self.sell_attempts,
                    "order": order.to_alpaca_payload(),
                    "snapshot": refreshed.to_dict(),
                }

            self.log.append(event)
            try:
                response = self.client.submit_order(order)
            except Exception as exc:  # noqa: BROAD_EXCEPT_OK
                event["event"] = "sell_order_error"
                event["error"] = f"{type(exc).__name__}:{exc}"
                self.log.append(event)
                return self._finish(
                    "blocked",
                    "order_submission_outcome_unknown",
                    market_date,
                    {"last_error": event["error"], "snapshot": refreshed.to_dict()},
                )

            if not broker_response_submitted(response):
                response_status = broker_response_status(response)
                event["event"] = "sell_order_rejected"
                event["reason"] = f"order_response_not_submitted:{response_status}"
                event["response"] = response
                self.log.append(event)
                return self._finish(
                    "blocked",
                    event["reason"],
                    market_date,
                    {"response": response, "snapshot": refreshed.to_dict()},
                )

            self.accepted_sell_order = True
            event["event"] = "sell_order_submitted"
            event["submitted_order"] = True
            event["response"] = response
            self.log.append(event)
            self.output(f"SELL submitted: trigger={trigger} order={event['order']}")
            fill_result = self._wait_for_fill(market_date, trigger, order, response)
            if fill_result["status"] == "sold":
                return fill_result
            return fill_result

        return self._finish("blocked", "max_sell_retries_reached", market_date)

    def _wait_for_fill(
        self,
        market_date: str,
        trigger: str,
        order: OrderRequest,
        response: JsonObject,
    ) -> SellMonitorResult:
        deadline = time.monotonic() + self.config.fill_check_seconds
        last_snapshot: SellSnapshot | None = None
        while time.monotonic() <= deadline:
            self.sleeper(self.config.fill_poll_seconds)
            try:
                last_snapshot = self._snapshot(regular_market_session(self.clock()).to_dict())
            except Exception as exc:  # noqa: BROAD_EXCEPT_OK
                self.log.append(
                    {
                        "event": "fill_poll_error",
                        "market_date": market_date,
                        "symbol": self.config.symbol,
                        "side": "sell",
                        "submitted_order": False,
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )
                continue
            if last_snapshot.qty <= 0:
                return self._sold_result(
                    last_snapshot,
                    market_date,
                    "sell_filled",
                    {
                        "trigger": trigger,
                        "order": order.to_alpaca_payload(),
                        "response": response,
                    },
                )
        payload = {
            "status": "pending_fill",
            "reason": "sell_order_submitted_not_yet_confirmed_filled",
            "market_date": market_date,
            "symbol": self.config.symbol,
            "side": "sell",
            "submitted_order": True,
            "trigger": trigger,
            "attempts": self.sell_attempts,
            "order": order.to_alpaca_payload(),
            "response": response,
            "snapshot": last_snapshot.to_dict() if last_snapshot else None,
        }
        self.log.append({"event": "sell_pending_fill", **payload})
        return payload

    def _sold_result(
        self,
        snapshot: SellSnapshot,
        market_date: str,
        reason: str,
        extra: JsonObject | None = None,
    ) -> SellMonitorResult:
        exit_price = snapshot.current_price if snapshot.current_price > 0 else 0.0
        entry_price = self.entry_price_for_pnl or snapshot.avg_entry_price
        estimated_pnl = (
            (exit_price - entry_price) * self.config.qty
            if exit_price > 0 and entry_price > 0
            else 0.0
        )
        estimated_pnl_pct = (
            (exit_price / entry_price - 1) * 100
            if exit_price > 0 and entry_price > 0
            else 0.0
        )
        payload = {
            "status": "sold",
            "reason": reason,
            "market_date": market_date,
            "symbol": self.config.symbol,
            "side": "sell",
            "submitted_order": False,
            "filled_confirmed": snapshot.qty <= 0,
            "estimated_exit_price": round(exit_price, 4),
            "avg_entry_price": round(entry_price, 4),
            "estimated_realized_pnl": round(estimated_pnl, 4),
            "estimated_realized_pnl_pct": round(estimated_pnl_pct, 4),
            "snapshot": snapshot.to_dict(),
        }
        if extra:
            payload.update(extra)
            if extra.get("response") is not None:
                payload["submitted_order"] = True
        self.log.append({"event": "sell_monitor_done", **payload})
        self.output(
            "SELL DONE "
            f"reason={reason} estimated_pnl={payload['estimated_realized_pnl']} "
            f"estimated_pnl_pct={payload['estimated_realized_pnl_pct']}"
        )
        return payload

    def _finish(
        self,
        status: str,
        reason: str,
        market_date: str,
        extra: JsonObject | None = None,
    ) -> SellMonitorResult:
        payload = {
            "status": status,
            "reason": reason,
            "market_date": market_date,
            "symbol": self.config.symbol,
            "side": "sell",
            "submitted_order": False,
        }
        if extra:
            payload.update(extra)
        self.log.append({"event": "sell_monitor_finish", **payload})
        self.output(f"SELL MONITOR {status}: {reason}")
        return payload
