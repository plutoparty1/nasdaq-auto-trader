from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

from .market_hours import regular_market_session
from .sell_monitor_execution import SellMonitorExecutionMixin
from .sell_monitor_log import SellMonitorLog
from .sell_monitor_rules import SellMonitorRulesMixin
from .sell_monitor_snapshot import SellMonitorSnapshotMixin
from .sell_monitor_types import HiveSellMonitorConfig, SellMonitorClient


class HiveSellMonitor(
    SellMonitorSnapshotMixin,
    SellMonitorRulesMixin,
    SellMonitorExecutionMixin,
):
    def __init__(
        self,
        client: SellMonitorClient,
        config: HiveSellMonitorConfig | None = None,
        log: SellMonitorLog | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        output: Callable[[str], None] = print,
    ) -> None:
        self.client = client
        self.config = config or HiveSellMonitorConfig()
        self.log = log or SellMonitorLog(self.config.record_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper
        self.output = output
        self.high_water_price = 0.0
        self.sell_attempts = 0
        self.accepted_sell_order = False
        self.entry_price_for_pnl = 0.0

    def run(self, max_loops: int | None = None) -> SellMonitorResult:
        """Run until sold, blocked, market close, or max loops is reached."""

        self._validate_config()
        loops = 0
        while True:
            loops += 1
            session = regular_market_session(self.clock())
            market_date = session.market_time[:10]
            if not session.is_open:
                return self._finish(
                    "blocked",
                    "market_not_open",
                    market_date,
                    {"session": session.to_dict()},
                )

            if self.log.has_unresolved_sell(self.config.symbol):
                return self._finish(
                    "blocked", "order_submission_outcome_unknown", market_date
                )

            try:
                snapshot = self._snapshot(session.to_dict())
            except Exception as exc:  # noqa: BROAD_EXCEPT_OK
                return self._finish(
                    "blocked",
                    f"snapshot_error:{type(exc).__name__}:{exc}",
                    market_date,
                )

            self._print_status(snapshot)
            no_position_result = self._handle_no_or_unexpected_position(
                snapshot,
                market_date,
            )
            if no_position_result is not None:
                return no_position_result

            if self.accepted_sell_order or self.log.has_submitted_sell_today(
                self.config.symbol,
                market_date,
            ):
                if snapshot.qty <= 0:
                    return self._sold_result(snapshot, market_date, "position_closed")
                self.output("Existing sell order recorded; polling position only.")
                self.log.append(
                    {
                        "event": "pending_sell_poll",
                        "market_date": market_date,
                        "symbol": self.config.symbol,
                        "side": "sell",
                        "submitted_order": False,
                        "snapshot": snapshot.to_dict(),
                    }
                )
            else:
                trigger = self._sell_trigger(snapshot)
                if trigger is not None:
                    result = self._submit_sell(snapshot, trigger, market_date)
                    if result["status"] in ("sold", "blocked", "dry_run_submitted"):
                        return result
                else:
                    self._record_hold_decision(snapshot, market_date)

            if max_loops is not None and loops >= max_loops:
                return self._finish(
                    "running",
                    "max_loops_reached",
                    market_date,
                    {"snapshot": snapshot.to_dict()},
                )
            self.sleeper(self.config.poll_seconds)
