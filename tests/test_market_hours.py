import unittest
from datetime import datetime, timezone

from nasdaq_auto_trader.market_hours import regular_market_session


class MarketHoursTests(unittest.TestCase):
    def test_regular_market_session_serializes_json_safe_session_details(self):
        session = regular_market_session(datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc))

        payload = session.to_dict()

        self.assertTrue(payload["is_open"])
        self.assertEqual(payload["reason"], "regular_market_open")
        self.assertEqual(payload["timezone"], "America/New_York")
        self.assertIn("opens_at", payload)
        self.assertIn("closes_at", payload)


if __name__ == "__main__":
    unittest.main()
