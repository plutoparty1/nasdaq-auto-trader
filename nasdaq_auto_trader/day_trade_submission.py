from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Callable

from .broker_response import broker_response_status, broker_response_submitted
from .day_trade_live import (
    _evaluate_live_buy_confirmation,
    _live_buy_preview,
    _print_live_buy_confirmation,
    assert_live_order_allowed,
    build_live_buy_confirmation_phrase,
)
from .day_trade_types import DayTradePlan, DayTradeSubmissionResult, DayTradeTradingClient
from .models import OrderRequest


class DayTradeSubmissionMixin:
    def submit_live_buy_order(
        self,
        client: DayTradeTradingClient,
        plan: DayTradePlan,
        dry_run: bool,
        live_trading: bool,
        confirm_input: Callable[[str], str] = input,
        output: Callable[[str], None] = print,
    ) -> DayTradeSubmissionResult:
        """Submit the planned buy order only after final explicit confirmation."""

        assert_live_order_allowed(dry_run=dry_run, live_trading=live_trading)
        result: DayTradeSubmissionResult = {
            "status": "not_submitted",
            "submitted_order": False,
            "reason": None,
            "preview": None,
            "confirmation": None,
            "response": None,
        }

        if plan.get("status") != "planned" or not plan.get("buy_order"):
            result["status"] = "blocked"
            result["reason"] = "plan_not_orderable"
            self._record_submission_result(plan, result)
            return result

        market_date = str(plan.get("market_date") or "")
        if self.record_store.has_live_buy_today(market_date):
            result["status"] = "blocked"
            result["reason"] = "live_buy_already_recorded_today"
            self._record_submission_result(plan, result)
            return result

        preview = _live_buy_preview(plan)
        phrase = build_live_buy_confirmation_phrase(plan)
        tolerance_pct = max(0.0, self.config.confirmation_price_tolerance_pct)
        result["preview"] = preview
        result["required_confirmation"] = phrase
        result["confirmation_price_tolerance_pct"] = tolerance_pct
        _print_live_buy_confirmation(preview, phrase, tolerance_pct, output)
        try:
            answer = confirm_input(f"Type exactly '{phrase}' to submit: ")
        except EOFError:
            answer = ""

        confirmation = _evaluate_live_buy_confirmation(
            answer,
            preview,
            phrase,
            tolerance_pct,
        )
        result["confirmation"] = confirmation
        if not confirmation["accepted"]:
            result["status"] = "cancelled"
            result["reason"] = confirmation["reason"]
            self._record_submission_result(plan, result)
            return result

        assert_live_order_allowed(dry_run=dry_run, live_trading=live_trading)
        order = OrderRequest(
            symbol=preview["ticker"],
            side="buy",
            type="limit",
            time_in_force="day",
            qty=preview["qty"],
            limit_price=preview["limit_price"],
        )
        estimated_cash = preview["estimated_amount"]
        order_cash = float(order.qty or 0) * float(order.limit_price or 0)
        try:
            account = client.get_account(refresh=True)
            buying_power = client.get_overseas_buying_power(
                order.symbol,
                order.limit_price,
            )
        except Exception as exc:  # noqa: BROAD_EXCEPT_OK
            result["status"] = "blocked"
            result["reason"] = f"cash_check_api_error:{type(exc).__name__}"
            self._record_submission_result(plan, result)
            return result
        if (
            not isfinite(estimated_cash)
            or estimated_cash <= 0
            or not isfinite(order_cash)
            or order_cash <= 0
            or not isfinite(account.cash)
        ):
            result["status"] = "blocked"
            result["reason"] = "deposited_cash_insufficient"
            self._record_submission_result(plan, result)
            return result
        required_cash = max(estimated_cash, order_cash)
        if account.cash < required_cash:
            result["status"] = "blocked"
            result["reason"] = "deposited_cash_insufficient"
            self._record_submission_result(plan, result)
            return result
        if not isfinite(buying_power) or buying_power < required_cash:
            result["status"] = "blocked"
            result["reason"] = "buying_power_insufficient"
            self._record_submission_result(plan, result)
            return result
        try:
            response = client.submit_order(order)
        except Exception as exc:  # noqa: BROAD_EXCEPT_OK
            result["status"] = "blocked"
            result["reason"] = f"order_api_error:{type(exc).__name__}:{exc}"
            self._record_submission_result(plan, result)
            return result
        if not broker_response_submitted(response):
            response_status = broker_response_status(response)
            reconcile_required = response_status in {
                "order_response_missing_status",
                "unknown",
            }
            result["status"] = "blocked"
            result["reason"] = (
                "order_response_reconcile_required"
                if reconcile_required
                else f"order_response_not_submitted:{response_status}"
            )
            result["terminal"] = reconcile_required
            result["response"] = response
            self._record_submission_result(plan, result)
            return result
        result.update(
            {
                "status": "submitted",
                "submitted_order": True,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "order": order.to_alpaca_payload(),
                "response": response,
            }
        )
        plan["submitted_order"] = True
        plan["buy_order"]["submitted_order"] = True
        self._record_submission_result(plan, result)
        return result

    def _record_submission_result(
        self,
        plan: DayTradePlan,
        result: DayTradeSubmissionResult,
    ) -> None:
        buy_order = plan.get("buy_order") or {}
        self.record_store.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "market_date": plan.get("market_date"),
                "strategy": plan.get("strategy"),
                "status": result.get("status"),
                "reason": result.get("reason"),
                "action": "buy" if buy_order else "none",
                "symbol": buy_order.get("symbol"),
                "dry_run": plan.get("dry_run"),
                "live_trading": plan.get("live_trading"),
                "submitted_order": result.get("submitted_order") is True,
                "terminal": result.get("terminal") is True,
                "preview": result.get("preview"),
                "response": result.get("response"),
            }
        )
