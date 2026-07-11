from __future__ import annotations

from datetime import datetime, timedelta

from .models import AccountSnapshot, Position
from .sell_monitor_math import _first_float
from .sell_monitor_types import JsonObject, SellMonitorResult, SellSnapshot


class SellMonitorSnapshotMixin:
    def _snapshot(self, session: JsonObject) -> SellSnapshot:
        account = self.client.get_account(refresh=True)
        positions = self.client.list_positions(refresh=True)
        position = positions.get(self.config.symbol)
        detail = self.client.get_price_detail(self.config.symbol)
        quote = self.client.get_best_quote(self.config.symbol)
        current_price = _first_float(detail, quote, "last", "ovrs_nmix_prpr", "stck_prpr")
        bid = _first_float(quote, detail, "pbid1", "bid")
        ask = _first_float(quote, detail, "pask1", "ask")
        qty = position.qty if position is not None else 0.0
        avg_entry_price = position.avg_entry_price if position is not None else 0.0
        if position is not None and self.entry_price_for_pnl <= 0:
            self.entry_price_for_pnl = avg_entry_price
        self.high_water_price = max(self.high_water_price, current_price)
        trailing_stop_price = None
        if self.high_water_price > avg_entry_price > 0:
            trailing_stop_price = self.high_water_price * (
                1 - self.config.trailing_stop_pct / 100
            )
        take_profit_price = avg_entry_price * (1 + self.config.take_profit_pct / 100)
        stop_loss_price = avg_entry_price * (1 + self.config.stop_loss_pct / 100)
        market_time = datetime.fromisoformat(session["market_time"])
        closes_at = datetime.fromisoformat(session["closes_at"])
        force_sell_at = closes_at - timedelta(
            minutes=self.config.force_sell_before_close_minutes
        )
        pnl_pct = (
            (current_price / avg_entry_price - 1) * 100
            if current_price > 0 and avg_entry_price > 0
            else 0.0
        )
        if market_time >= closes_at:
            force_sell_at = market_time
        return SellSnapshot(
            session=session,
            account=account,
            position=position,
            current_price=current_price,
            bid=bid,
            ask=ask,
            avg_entry_price=avg_entry_price,
            qty=qty,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            trailing_stop_price=trailing_stop_price,
            force_sell_at=force_sell_at.isoformat(),
            pnl_pct=pnl_pct,
        )

    def _handle_no_or_unexpected_position(
        self,
        snapshot: SellSnapshot,
        market_date: str,
    ) -> SellMonitorResult | None:
        if snapshot.qty <= 0:
            return self._sold_result(snapshot, market_date, "already_sold")
        if abs(snapshot.qty - self.config.qty) > 1e-8:
            return self._finish(
                "blocked",
                "unexpected_hive_position_qty",
                market_date,
                {"snapshot": snapshot.to_dict()},
            )
        if snapshot.avg_entry_price <= 0:
            return self._finish(
                "blocked",
                "missing_avg_entry_price",
                market_date,
                {"snapshot": snapshot.to_dict()},
            )
        if snapshot.current_price <= 0:
            return self._finish(
                "blocked",
                "missing_current_price",
                market_date,
                {"snapshot": snapshot.to_dict()},
            )
        return None

    def _print_status(self, snapshot: SellSnapshot) -> None:
        trailing = (
            f"{snapshot.trailing_stop_price:.4f}"
            if snapshot.trailing_stop_price is not None
            else "inactive"
        )
        self.output(
            "HIVE sell monitor "
            f"qty={snapshot.qty:.0f} avg={snapshot.avg_entry_price:.4f} "
            f"current={snapshot.current_price:.4f} bid={snapshot.bid:.4f} "
            f"ask={snapshot.ask:.4f} pnl_pct={snapshot.pnl_pct:.4f} "
            f"tp={snapshot.take_profit_price:.4f} "
            f"sl={snapshot.stop_loss_price:.4f} trailing={trailing} "
            f"dry_run={self.config.dry_run} "
            f"sell_only={self.config.sell_only} "
            f"allow_additional_buy={self.config.allow_additional_buy} "
            f"stop_loss_enabled={self.config.stop_loss_enabled} "
            f"trailing_stop_enabled={self.config.trailing_stop_enabled} "
            f"force_sell_before_close_enabled="
            f"{self.config.force_sell_before_close_enabled} "
            f"sell_only_when_profit={self.config.sell_only_when_profit} "
            f"hold_if_unprofitable={self.config.hold_if_unprofitable} "
            f"require_confirm_before_loss_sell="
            f"{self.config.require_confirm_before_loss_sell} "
            f"force_at={snapshot.force_sell_at}"
        )
