import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent, AuditLogger
from nasdaq_auto_trader.app_types import PortfolioSnapshot
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.daily_report import DailyReportService, _summarize_audit
from nasdaq_auto_trader.models import AccountSnapshot


SEOUL = ZoneInfo("Asia/Seoul")


class DailyReportTests(unittest.TestCase):
    def test_delayed_learning_is_counted_on_its_completed_market_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            AuditLogger(audit_path).append(
                AuditEvent(
                    "learning_completed",
                    timestamp="2026-07-20T14:00:00+00:00",
                    payload={
                        "market_date": "2026-07-17",
                        "generated_candidates": 3,
                        "accepted_candidates": 1,
                    },
                )
            )

            friday = _summarize_audit(audit_path, "2026-07-17")
            monday = _summarize_audit(audit_path, "2026-07-20")

        self.assertEqual(friday.generated_candidates, 3)
        self.assertEqual(friday.accepted_candidates, 1)
        self.assertEqual(monday.generated_candidates, 0)

    def test_latest_report_ignores_backup_files_with_non_date_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            expected = reports / "daily-2026-07-17.md"
            expected.write_text("current", encoding="utf-8")
            (reports / "daily-2026-07-17.pre-cleanup.md").write_text(
                "backup",
                encoding="utf-8",
            )
            service = DailyReportService(reports, root / "audit.jsonl")

            latest = service.latest_path()

        self.assertEqual(latest, expected)

    def test_report_is_due_once_after_local_morning_cutoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = DailyReportService(root / "reports", root / "audit.jsonl")
            settings = TradingSettings(
                daily_report_hour=8,
                daily_report_minute=0,
            )
            before = datetime(2026, 7, 18, 7, 59, tzinfo=SEOUL)
            due = datetime(2026, 7, 18, 8, 0, tzinfo=SEOUL)

            self.assertFalse(service.is_due(before, settings))
            self.assertTrue(service.is_due(due, settings))
            result = service.generate(due, settings, None)
            self.assertFalse(service.is_due(due, settings))

        self.assertEqual(result.market_date, "2026-07-17")

    def test_aware_utc_clock_is_converted_to_machine_local_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = DailyReportService(root / "reports", root / "audit.jsonl")
            local_zone = datetime.now().astimezone().tzinfo
            local_morning = datetime(2026, 7, 18, 8, 0, tzinfo=local_zone)

            self.assertTrue(
                service.is_due(
                    local_morning.astimezone(timezone.utc),
                    TradingSettings(daily_report_hour=8, daily_report_minute=0),
                )
            )

    def test_report_uses_latest_completed_nasdaq_day_across_weekend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = DailyReportService(root / "reports", root / "audit.jsonl")

            saturday = datetime(2026, 7, 18, 8, 0, tzinfo=SEOUL)
            monday = datetime(2026, 7, 20, 8, 0, tzinfo=SEOUL)

            self.assertEqual(service.target_market_date(saturday), "2026-07-17")
            self.assertEqual(service.target_market_date(monday), "2026-07-17")

    def test_report_uses_prior_session_across_holiday_and_winter_dst(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = DailyReportService(root / "reports", root / "audit.jsonl")

            independence_day = datetime(2026, 7, 4, 8, 0, tzinfo=SEOUL)
            winter_monday = datetime(2026, 12, 7, 8, 0, tzinfo=SEOUL)

            self.assertEqual(service.target_market_date(independence_day), "2026-07-02")
            self.assertEqual(service.target_market_date(winter_monday), "2026-12-04")

    def test_report_summarizes_runtime_and_order_audits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "audit.jsonl"
            audit = AuditLogger(audit_path)
            timestamp = "2026-07-17T14:00:00+00:00"
            audit.append(
                AuditEvent(
                    "operating_transition",
                    timestamp=timestamp,
                    payload={"state": "LIVE_TRADING", "reason": "preflight_passed"},
                )
            )
            audit.append(
                AuditEvent(
                    "learning_completed",
                    timestamp=timestamp,
                    payload={
                        "generated_candidates": 2,
                        "accepted_candidates": 1,
                        "submitted_orders": 0,
                    },
                )
            )
            audit.append(
                AuditEvent(
                    "automatic_order_submitted",
                    timestamp=timestamp,
                    payload={"broker_submitted": True},
                )
            )
            audit.append(
                AuditEvent(
                    "automatic_order_blocked",
                    timestamp=timestamp,
                    payload={"reason": "max_daily_buy_count_reached"},
                )
            )
            service = DailyReportService(root / "reports", audit_path)
            snapshot = PortfolioSnapshot(
                as_of=datetime(2026, 7, 17, 23, 0, tzinfo=SEOUL),
                mode="dry_run",
                broker="kis",
                account=AccountSnapshot(64.83, 64.83, 64.83),
                positions=[],
            )

            result = service.generate(
                datetime(2026, 7, 18, 8, 0, tzinfo=SEOUL),
                TradingSettings(),
                snapshot,
            )
            text = result.path.read_text(encoding="utf-8")

        self.assertEqual(result.submitted_orders, 1)
        self.assertEqual(result.blocked_orders, 1)
        self.assertIn("생성 후보 | 2", text)
        self.assertIn("검증 통과 후보 | 1", text)
        self.assertIn("64.83", text)

    def test_report_survives_corrupt_audit_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "audit.jsonl"
            audit_path.write_text(
                "{broken\n"
                '{"event_type":"automatic_order_blocked",'
                '"timestamp":"2026-07-17T14:00:00+00:00",'
                '"payload":{"reason":"risk_config_invalid"}}\n',
                encoding="utf-8",
            )
            service = DailyReportService(root / "reports", audit_path)

            result = service.generate(
                datetime(2026, 7, 18, 8, 0, tzinfo=SEOUL),
                TradingSettings(),
                None,
            )

        self.assertEqual(result.blocked_orders, 1)
        self.assertEqual(result.skipped_audit_lines, 1)

    def test_report_allowlist_rejects_secret_shaped_payload_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "audit.jsonl"
            AuditLogger(audit_path).append(
                AuditEvent(
                    "automatic_order_blocked",
                    timestamp="2026-07-17T14:00:00+00:00",
                    payload={
                        "reason": "KIS_APP_SECRET=supersecret",
                        "account_no": "12345678",
                        "token": "private-token",
                    },
                )
            )
            service = DailyReportService(root / "reports", audit_path)

            result = service.generate(
                datetime(2026, 7, 18, 8, 0, tzinfo=SEOUL),
                TradingSettings(),
                None,
            )
            text = result.path.read_text(encoding="utf-8")

        self.assertNotIn("supersecret", text)
        self.assertNotIn("12345678", text)
        self.assertNotIn("private-token", text)

    def test_report_ignores_reasons_from_unrelated_audit_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "audit.jsonl"
            AuditLogger(audit_path).append(
                AuditEvent(
                    "research_internal_event",
                    timestamp="2026-07-17T14:00:00+00:00",
                    payload={"reason": "unrelated_internal_reason"},
                )
            )
            service = DailyReportService(root / "reports", audit_path)

            result = service.generate(
                datetime(2026, 7, 18, 8, 0, tzinfo=SEOUL),
                TradingSettings(),
                None,
            )
            text = result.path.read_text(encoding="utf-8")

        self.assertIn("차단 또는 점검 사유: 없음", text)


if __name__ == "__main__":
    unittest.main()
