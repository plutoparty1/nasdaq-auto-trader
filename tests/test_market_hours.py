import unittest
from datetime import datetime, timezone

from nasdaq_auto_trader.market_hours import latest_completed_market_date, regular_market_session


class MarketHoursTests(unittest.TestCase):
    def test_latest_completed_market_date_ignores_open_session(self):
        completed = latest_completed_market_date(
            datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)
        )

        self.assertEqual(completed, "2026-07-15")
    def test_regular_market_session_serializes_json_safe_session_details(self):
        session = regular_market_session(datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc))

        payload = session.to_dict()

        self.assertTrue(payload["is_open"])
        self.assertEqual(payload["reason"], "regular_market_open")
        self.assertEqual(payload["timezone"], "America/New_York")
        self.assertIn("opens_at", payload)
        self.assertIn("closes_at", payload)

    def test_weekend_is_closed(self):
        session = regular_market_session(datetime(2026, 7, 11, 15, 0, tzinfo=timezone.utc))
        self.assertFalse(session.is_open)
        self.assertEqual(session.reason, "weekend")

    def test_independence_day_observed_is_closed(self):
        session = regular_market_session(datetime(2026, 7, 3, 15, 0, tzinfo=timezone.utc))
        self.assertFalse(session.is_open)
        self.assertEqual(session.reason, "market_holiday")

    def test_thanksgiving_following_session_closes_early(self):
        before_close = regular_market_session(datetime(2026, 11, 27, 17, 30, tzinfo=timezone.utc))
        after_close = regular_market_session(datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc))
        self.assertTrue(before_close.is_open)
        self.assertFalse(after_close.is_open)
        self.assertEqual(after_close.reason, "after_regular_close")
        self.assertIn("13:00:00-05:00", after_close.closes_at)

    def test_dst_changes_utc_open_time(self):
        winter = regular_market_session(datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc))
        summer = regular_market_session(datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc))
        self.assertTrue(winter.is_open)
        self.assertTrue(summer.is_open)
        self.assertIn("09:30:00-05:00", winter.opens_at)
        self.assertIn("09:30:00-04:00", summer.opens_at)

if __name__ == "__main__":
    unittest.main()
