from __future__ import annotations

from datetime import datetime

from .models import OrderRequest
from .sell_monitor_math import _floor_to_cent
from .sell_monitor_types import (
    HIVE_SYMBOL,
    SellMonitorConfigError,
    SellMonitorSafetyError,
    SellSnapshot,
)


class SellMonitorRulesMixin:
    def _validate_config(self) -> None:
        if self.config.symbol != HIVE_SYMBOL:
            raise SellMonitorConfigError("sell monitor is locked to HIVE only")
        if self.config.qty != 1:
            raise SellMonitorConfigError("sell monitor is locked to exactly 1 share")
        if not self.config.sell_only:
            raise SellMonitorConfigError("sell monitor must run with sell_only=true")
        if self.config.allow_additional_buy:
            raise SellMonitorConfigError("allow_additional_buy must be false")
        if self.config.max_retries < 1:
            raise SellMonitorConfigError("max_retries must be at least 1")

    def _sell_trigger(self, snapshot: SellSnapshot) -> str | None:
        market_time = datetime.fromisoformat(snapshot.session["market_time"])
        force_sell_at = datetime.fromisoformat(snapshot.force_sell_at)
        is_profit = snapshot.current_price > snapshot.avg_entry_price
        if self.config.sell_only_when_profit and not is_profit:
            return None
        if is_profit and snapshot.pnl_pct >= self.config.take_profit_pct:
            return "take_profit"
        if (
            self.config.stop_loss_enabled
            and snapshot.current_price <= snapshot.stop_loss_price
        ):
            if snapshot.pnl_pct < 0 and self.config.require_confirm_before_loss_sell:
                return None
            return "stop_loss"
        if (
            self.config.trailing_stop_enabled
            and snapshot.trailing_stop_price is not None
            and snapshot.current_price <= snapshot.trailing_stop_price
        ):
            if self.config.sell_only_when_profit and not is_profit:
                return None
            if snapshot.pnl_pct < 0 and self.config.require_confirm_before_loss_sell:
                return None
            return "trailing_stop"
        if (
            self.config.force_sell_before_close_enabled
            and self.config.max_hold_until_market_close
            and market_time >= force_sell_at
        ):
            if self.config.sell_only_when_profit and not is_profit:
                return None
            if snapshot.pnl_pct < 0 and self.config.require_confirm_before_loss_sell:
                return None
            return "force_before_close"
        return None

    def _record_hold_decision(self, snapshot: SellSnapshot, market_date: str) -> None:
        reason = self._hold_reason(snapshot)
        if reason is None:
            return
        if reason == "hold_unprofitable":
            message = "HOLD: 손실 상태이므로 매도하지 않음"
        elif reason == "hold_not_profitable":
            message = "HOLD: 수익 상태가 아니므로 매도하지 않음"
        else:
            message = "HOLD: 익절 조건 미충족으로 보유"
        self.output(message)
        self.log.append(
            {
                "event": reason,
                "status": "hold",
                "reason": reason,
                "market_date": market_date,
                "symbol": self.config.symbol,
                "side": "sell",
                "submitted_order": False,
                "snapshot": snapshot.to_dict(),
            }
        )

    def _hold_reason(self, snapshot: SellSnapshot) -> str | None:
        if self.config.hold_if_unprofitable and snapshot.pnl_pct < 0:
            return "hold_unprofitable"
        if (
            self.config.sell_only_when_profit
            and snapshot.current_price <= snapshot.avg_entry_price
        ):
            return "hold_not_profitable"
        if snapshot.pnl_pct < self.config.take_profit_pct:
            return "hold_take_profit_not_reached"
        return None

    def _build_sell_order(self, snapshot: SellSnapshot) -> OrderRequest:
        reference = snapshot.bid if snapshot.bid > 0 else snapshot.current_price
        raw_limit = reference * (1 - self.config.marketable_limit_buffer_pct / 100)
        limit_price = _floor_to_cent(max(raw_limit, 0.01))
        return OrderRequest(
            symbol=self.config.symbol,
            side="sell",
            type="limit",
            time_in_force="day",
            qty=self.config.qty,
            limit_price=limit_price,
        )

    def _assert_sell_order_allowed(
        self,
        order: OrderRequest,
        snapshot: SellSnapshot,
    ) -> None:
        if order.symbol != HIVE_SYMBOL:
            raise SellMonitorSafetyError("blocked non-HIVE order")
        if order.side != "sell":
            raise SellMonitorSafetyError("blocked non-sell order")
        if order.qty is None or order.qty > snapshot.qty:
            raise SellMonitorSafetyError("blocked sell quantity above held quantity")
        if abs(order.qty - self.config.qty) > 1e-8:
            raise SellMonitorSafetyError("blocked sell quantity other than 1")
