import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.config_manager import TradingSettings, settings_from_dict, validate_settings
from nasdaq_auto_trader.session_claims import ClaimStatus, SignalKey
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from nasdaq_auto_trader.unattended_policy import is_recoverable_preorder_failure


class UnattendedPolicyTests(unittest.TestCase):
    def test_unattended_defaults_are_backward_compatible(self):
        settings = settings_from_dict({"ticker": "QQQ"})

        self.assertFalse(settings.unattended_operation_enabled)
        self.assertFalse(settings.unattended_live_trading_enabled)
        self.assertEqual(settings.unattended_interval_minutes, 15)
        self.assertTrue(settings.daily_report_enabled)
        self.assertEqual(settings.daily_report_hour, 8)
        self.assertEqual(settings.daily_report_minute, 0)
        self.assertEqual(settings.daily_report_retention_days, 90)

    def test_unattended_schedule_values_are_validated(self):
        cases = (
            TradingSettings(unattended_interval_minutes=0),
            TradingSettings(daily_report_hour=24),
            TradingSettings(daily_report_minute=60),
            TradingSettings(daily_report_retention_days=0),
        )

        for settings in cases:
            with self.subTest(settings=settings):
                self.assertFalse(validate_settings(settings).ok)

    def test_only_preorder_failures_are_recoverable(self):
        for reason in (
            "market_data_unavailable",
            "broker_unavailable",
            "account_state_unavailable",
        ):
            with self.subTest(reason=reason):
                self.assertTrue(is_recoverable_preorder_failure(reason))

        for reason in (
            "order_outcome_audit_failed_reconcile_required",
            "claim_finalization_failed_reconcile_required",
            "signal_key_uncertain",
            "risk_config_invalid",
            "unknown_failure",
        ):
            with self.subTest(reason=reason):
                self.assertFalse(is_recoverable_preorder_failure(reason))

    def test_interrupted_claim_recovers_uncertain_and_blocks_same_signal(self):
        key = SignalKey(
            "2026-07-17",
            "strategy-1",
            "v1",
            "AAPL",
            "buy",
            "2026-07-17T14:00:00+00:00",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            first = TradingSessionStore(path)
            self.assertTrue(first.claim(key).granted)

            restarted = TradingSessionStore(path)
            self.assertEqual(restarted.recover_interrupted_claims(), 1)
            duplicate = restarted.claim(key)

        self.assertFalse(duplicate.granted)
        self.assertEqual(duplicate.status, ClaimStatus.UNCERTAIN)
        self.assertEqual(duplicate.reason, "signal_key_uncertain")


if __name__ == "__main__":
    unittest.main()
