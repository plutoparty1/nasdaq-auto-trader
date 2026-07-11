from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .day_trade_pricing import _unique_symbols
from .day_trade_types import CandidateEvaluation, DayTradeDataClient, DayTradePlan, JsonObject
from .market_hours import regular_market_session


class DayTradePlanMixin:
    def build_plan(
        self,
        client: DayTradeDataClient,
        candidate_symbols: list[str],
        dry_run: bool = True,
        live_trading: bool = False,
        now: datetime | None = None,
    ) -> DayTradePlan:
        """Evaluate candidates and return an order plan without submitting orders."""

        if not dry_run and not live_trading:
            raise DayTradePlanError("dry_run=False requires live_trading=True")

        session = regular_market_session(now)
        market_date = session.market_time[:10]
        evaluations = [
            self._evaluate_candidate(client, symbol)
            for symbol in _unique_symbols(candidate_symbols)
        ]
        selected = self._select_affordable_candidate(client, evaluations)

        blockers: list[str] = []
        if not session.is_open:
            blockers.append(f"market_not_open:{session.reason}")
        if live_trading and self.record_store.has_live_buy_today(market_date):
            blockers.append("live_buy_already_recorded_today")
        if selected is None:
            blockers.append("no_candidate_passed_filters_and_buying_power")

        plan = self._plan_from_selection(
            selected,
            session.to_dict(),
            market_date,
            blockers,
            dry_run,
            live_trading,
        )
        plan["candidates"] = [evaluation.to_dict() for evaluation in evaluations]
        self._record_plan(plan)
        return plan

    def _plan_from_selection(
        self,
        selected: CandidateEvaluation | None,
        session: JsonObject,
        market_date: str,
        blockers: list[str],
        dry_run: bool,
        live_trading: bool,
    ) -> DayTradePlan:
        status = "blocked" if blockers else "planned"
        plan: DayTradePlan = {
            "strategy": "one_share_same_day_test",
            "status": status,
            "blockers": blockers,
            "dry_run": dry_run,
            "live_trading": live_trading,
            "submitted_order": False,
            "market_date": market_date,
            "session": session,
            "settings": {
                "max_total_usd": self.config.max_total_usd,
                "qty": self.config.qty,
                "take_profit_pct": self.config.take_profit_pct,
                "stop_loss_pct": self.config.stop_loss_pct,
                "max_hold_minutes": self.config.max_hold_minutes,
                "force_exit_minutes_before_close": (
                    self.config.force_exit_minutes_before_close
                ),
                "fee_buffer_usd": self.config.fee_buffer_usd,
                "fee_buffer_pct": self.config.fee_buffer_pct,
                "confirmation_price_tolerance_pct": (
                    self.config.confirmation_price_tolerance_pct
                ),
            },
            "selected": None,
            "buy_order": None,
            "sell_plan": None,
        }
        if selected is None:
            return plan

        buy_limit = selected.buy_limit_price
        take_profit_price = buy_limit * (1 + self.config.take_profit_pct / 100)
        stop_loss_price = buy_limit * (1 + self.config.stop_loss_pct / 100)
        market_now = datetime.fromisoformat(session["market_time"])
        closes_at = datetime.fromisoformat(session["closes_at"])
        max_hold_exit = market_now + timedelta(minutes=self.config.max_hold_minutes)
        close_buffer_exit = closes_at - timedelta(
            minutes=self.config.force_exit_minutes_before_close
        )
        force_exit_at = min(max_hold_exit, close_buffer_exit)
        if force_exit_at <= market_now:
            plan["status"] = "blocked"
            plan["blockers"].append("too_close_to_market_close")

        plan["selected"] = selected.to_dict()
        plan["buy_order"] = {
            "side": "buy",
            "symbol": selected.symbol,
            "qty": self.config.qty,
            "order_type": "limit",
            "limit_price": round(buy_limit, 4),
            "estimated_required_amount": round(
                selected.estimated_required_amount,
                4,
            ),
            "buying_power": round(selected.buying_power, 4),
            "submitted_order": False,
        }
        plan["sell_plan"] = {
            "after_buy_filled": True,
            "side": "sell",
            "symbol": selected.symbol,
            "qty": self.config.qty,
            "order_type": "limit_or_stop_limit",
            "take_profit_limit_price": round(take_profit_price, 4),
            "stop_loss_trigger_price": round(stop_loss_price, 4),
            "force_exit_at": force_exit_at.isoformat(),
            "force_exit_order_type": "limit",
            "submitted_order": False,
        }
        return plan

    def _record_plan(self, plan: DayTradePlan) -> None:
        action = "buy" if plan.get("buy_order") else "none"
        self.record_store.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "market_date": plan["market_date"],
                "strategy": plan["strategy"],
                "status": plan["status"],
                "action": action,
                "symbol": (
                    plan["buy_order"]["symbol"] if plan.get("buy_order") else None
                ),
                "dry_run": plan["dry_run"],
                "live_trading": plan["live_trading"],
                "submitted_order": False,
                "plan": plan,
            }
        )
