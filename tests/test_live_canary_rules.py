from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from nasdaq_auto_trader.live_canary_rules import (
    CanaryEntryContext,
    CanaryExitSnapshot,
    entry_block_reason,
    exit_reason,
)
from nasdaq_auto_trader.market_hours import MarketSession


EASTERN = ZoneInfo("America/New_York")


class LiveCanaryRulesTests(unittest.TestCase):
    def test_entry_window_starts_fifteen_minutes_after_open_and_ends_thirty_before_close(self):
        session = _session()

        before = entry_block_reason(_entry_context(session, 9, 44))
        at_start = entry_block_reason(_entry_context(session, 9, 45))
        at_end = entry_block_reason(_entry_context(session, 15, 30))

        self.assertEqual(before, "entry_window_not_open")
        self.assertEqual(at_start, "")
        self.assertEqual(at_end, "entry_window_closed")

    def test_entry_is_blocked_by_position_attempt_and_round_trip_limits(self):
        session = _session()

        position = entry_block_reason(_entry_context(session, 12, 0, has_position=True))
        attempts = entry_block_reason(_entry_context(session, 12, 0, entry_attempts=3))
        round_trips = entry_block_reason(_entry_context(session, 12, 0, round_trips=3))

        self.assertEqual(position, "canary_position_active")
        self.assertEqual(attempts, "entry_attempt_limit_reached")
        self.assertEqual(round_trips, "round_trip_limit_reached")

    def test_exit_triggers_at_exact_plus_and_minus_five_percent(self):
        now = datetime(2026, 7, 17, 12, 0, tzinfo=EASTERN)

        take_profit = exit_reason(CanaryExitSnapshot(10.0, 10.5, now, _close()))
        stop_loss = exit_reason(CanaryExitSnapshot(10.0, 9.5, now, _close()))
        hold = exit_reason(CanaryExitSnapshot(10.0, 10.49, now, _close()))

        self.assertEqual(take_profit, "take_profit")
        self.assertEqual(stop_loss, "stop_loss")
        self.assertEqual(hold, "hold")

    def test_force_exit_begins_fifteen_minutes_before_early_close(self):
        early_close = datetime(2026, 11, 27, 13, 0, tzinfo=EASTERN)

        before = exit_reason(
            CanaryExitSnapshot(
                10.0,
                10.0,
                datetime(2026, 11, 27, 12, 44, tzinfo=EASTERN),
                early_close,
            )
        )
        at_cutoff = exit_reason(
            CanaryExitSnapshot(
                10.0,
                10.0,
                datetime(2026, 11, 27, 12, 45, tzinfo=EASTERN),
                early_close,
            )
        )

        self.assertEqual(before, "hold")
        self.assertEqual(at_cutoff, "force_exit")


def _session() -> MarketSession:
    return MarketSession(
        True,
        "regular_market_open",
        "2026-07-17T12:00:00-04:00",
        "2026-07-17T09:30:00-04:00",
        "2026-07-17T16:00:00-04:00",
    )


def _entry_context(
    session: MarketSession,
    hour: int,
    minute: int,
    *,
    has_position: bool = False,
    entry_attempts: int = 0,
    round_trips: int = 0,
) -> CanaryEntryContext:
    return CanaryEntryContext(
        session,
        datetime(2026, 7, 17, hour, minute, tzinfo=EASTERN),
        has_position,
        entry_attempts,
        round_trips,
    )


def _close() -> datetime:
    return datetime(2026, 7, 17, 16, 0, tzinfo=EASTERN)


if __name__ == "__main__":
    unittest.main()
