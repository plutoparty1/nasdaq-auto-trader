import queue
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nasdaq_auto_trader.app_ui_actions import DashboardActionsMixin
from nasdaq_auto_trader.app_ui_render import DashboardRenderMixin
from nasdaq_auto_trader.daily_report_models import DailyReportResult
from nasdaq_auto_trader.automation_coordinator import PreflightHealth
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.intraday_shadow_scan import IntradayShadowScanReport
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.app_controller_fixtures import IsolatedControllerTestCase


class Variable:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class PositionsTree:
    def get_children(self) -> tuple:
        return ()

    def insert(self, parent, index, values) -> None:
        del parent, index, values


class GuiAutoStartFeedbackTests(IsolatedControllerTestCase):
    def test_daily_report_result_is_visible_to_operator(self):
        view = DashboardRenderMixin()
        view.status_var = Variable()
        logs: list[str] = []
        view._append_log = logs.append
        result = DailyReportResult(
            "2026-07-17",
            Path("daily-2026-07-17.md"),
            4,
            1,
            2,
            0,
        )

        view._render_daily_report(result)

        self.assertIn("2026-07-17", view.status_var.value)
        self.assertTrue(any("제출 1건" in line and "차단 2건" in line for line in logs))

    def test_due_auto_cycle_takes_priority_over_due_daily_report(self):
        view = DashboardActionsMixin()
        view._worker = None
        view._next_portfolio_refresh = float("inf")
        view._daily_report_service = SimpleNamespace(is_due=lambda now, settings: True)
        view.controller = SimpleNamespace(
            is_due=lambda: True,
            run_operating_cycle=lambda: [],
            trading_settings=TradingSettings(),
            last_snapshot=None,
        )
        started: list[str] = []
        view._start_task = lambda label, task: started.append(label) or True
        view._update_controls = lambda: None
        view.root = SimpleNamespace(after=lambda delay, callback: None)

        view._tick()

        self.assertEqual(started, ["auto"])

    def test_safe_halt_reason_is_visible_when_auto_start_returns_no_results(self):
        view = DashboardRenderMixin()
        view.controller = SimpleNamespace(
            state="paused",
            last_error="operating_model_unavailable",
            selection_error=None,
            last_selection_report=None,
            trading_settings=SimpleNamespace(auto_symbol_selection_enabled=True),
        )
        view.status_var = Variable()
        logs: list[str] = []
        view._append_log = logs.append

        view._render_auto_results([])

        expected = "자동매매 안전정지: 검증 통과한 자동매매 전략이 없음"
        self.assertEqual(view.status_var.value, expected)
        self.assertEqual(logs, [expected])

    def test_shadow_scan_feedback_confirms_zero_orders(self):
        view = DashboardRenderMixin()
        report = IntradayShadowScanReport(
            datetime(2026, 7, 16, 15, 0, tzinfo=timezone.utc),
            "nasdaq-100",
            ("AAPL", "MSFT"),
            ("AAPL",),
            {"MSFT": ("abnormal_spread",)},
            False,
            Path("scan.json"),
        )
        view.controller = SimpleNamespace(
            state="running",
            last_error=None,
            selection_error=None,
            last_selection_report=None,
            last_shadow_scan=report,
            trading_settings=SimpleNamespace(auto_symbol_selection_enabled=True),
        )
        view.status_var = Variable()
        logs: list[str] = []
        view._append_log = logs.append

        view._render_auto_results([])

        self.assertIn("장중 무주문 스캔 완료", view.status_var.value)
        self.assertTrue(any("실제 주문 0건" in line for line in logs))

    def test_safe_halt_does_not_replace_feedback_with_portfolio_refresh(self):
        view = DashboardActionsMixin()
        view._result_queue = queue.Queue()
        view._result_queue.put(("ok", "auto", []))
        view._worker = None
        view.controller = SimpleNamespace(
            state="paused",
            refresh_portfolio=lambda: None,
        )
        rendered: list[list] = []
        started: list[str] = []
        view._render_auto_results = rendered.append
        view._start_task = lambda label, task: started.append(label) or True
        view._update_controls = lambda: None
        view.root = SimpleNamespace(after=lambda delay, callback: None)

        view._poll_results()

        self.assertEqual(rendered, [[]])
        self.assertEqual(started, [])

    def test_completed_worker_updates_controls_without_waiting_for_next_tick(self):
        view = DashboardActionsMixin()
        view._result_queue = queue.Queue()
        view._result_queue.put(("ok", "portfolio", "snapshot"))
        view._worker = object()
        view._render_snapshot = Mock()
        view._update_controls = Mock()
        view.portfolio_refresh_seconds = 60
        view.root = SimpleNamespace(after=lambda delay, callback: None)

        view._poll_results()

        self.assertIsNone(view._worker)
        view._render_snapshot.assert_called_once_with("snapshot")
        view._update_controls.assert_called_once_with()

    def test_periodic_portfolio_result_preserves_safe_halt_status(self):
        view = DashboardRenderMixin()
        view.controller = SimpleNamespace(
            state="paused",
            last_error="operating_model_unavailable",
            selection_error=None,
        )
        view.status_var = Variable()
        view.cash_var = Variable()
        view.equity_var = Variable()
        view.buying_power_var = Variable()
        view.updated_var = Variable()
        view.positions_tree = PositionsTree()
        view._append_log = lambda message: None
        snapshot = SimpleNamespace(
            account=SimpleNamespace(cash=64.83, equity=64.83, buying_power=64.83),
            positions=[],
            as_of=datetime(2026, 7, 16, tzinfo=timezone.utc),
        )

        view._render_snapshot(snapshot)

        self.assertEqual(
            view.status_var.value,
            "자동매매 안전정지: 검증 통과한 자동매매 전략이 없음",
        )

    def test_controller_refresh_preserves_safe_halt_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                engine_factory=lambda config: SimpleNamespace(
                    load_portfolio=lambda refresh=False: (
                        AccountSnapshot(cash=64.83, equity=64.83, buying_power=64.83),
                        {},
                    )
                ),
                clock=lambda: datetime(2026, 7, 16, 15, 0, tzinfo=timezone.utc),
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                ),
                session_store=TradingSessionStore(Path(temp_dir) / "session.json"),
                operating_store=self.operating_store(),
            )
            controller.start()
            with patch.object(
                controller,
                "_operating_health",
                return_value=PreflightHealth(account_ok=False),
            ):
                controller.run_operating_cycle(force=True)

            controller.refresh_portfolio()

        self.assertEqual(controller.state, "paused")
        self.assertEqual(controller.last_error, "account_state_unavailable")


if __name__ == "__main__":
    unittest.main()
