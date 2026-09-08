import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nasdaq_auto_trader.app_ui import DashboardApp
from nasdaq_auto_trader.app_types import PortfolioSnapshot, PositionRow
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.dry_run_market_data import DryRunMarketData
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.operating_state import OperatingStateStore
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.app_controller_fixtures import IsolatedControllerTestCase


class FixtureEngine:
    def __init__(self) -> None:
        self.market_data = DryRunMarketData()

    def load_portfolio(self, refresh: bool = False):
        del refresh
        return AccountSnapshot(cash=64.83, equity=64.83, buying_power=64.83), {}


class FixtureEngineFactory:
    def __call__(self, config, **kwargs) -> FixtureEngine:
        del config, kwargs
        return FixtureEngine()


class FixtureReportService:
    def __init__(self, report_path: Path) -> None:
        self.report_path = report_path

    def is_due(self, now, settings) -> bool:
        del now, settings
        return False

    def latest_path(self) -> Path:
        return self.report_path


@unittest.skipUnless(os.name == "nt", "Windows Tk E2E")
class WindowsGuiE2ETests(IsolatedControllerTestCase):
    def test_operator_buttons_complete_and_expose_failures_without_orders(self):
        import tkinter as tk
        from tkinter import ttk

        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                runtime_root = Path(temp_dir)
                report_path = runtime_root / "daily-2026-07-16.md"
                report_path.write_text("safe report", encoding="utf-8")
                controller = self.create_controller(
                    AppConfig(mode="dry_run", symbols=["QQQ"]),
                    engine_factory=FixtureEngineFactory(),
                    clock=lambda: datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
                    trading_settings=TradingSettings(
                        unattended_operation_enabled=False,
                        auto_symbol_selection_enabled=False,
                    ),
                    settings_path=runtime_root / "trading_config.json",
                    session_store=TradingSessionStore(runtime_root / "session.json"),
                    operating_store=OperatingStateStore(runtime_root / "operating.json"),
                )
                artifacts = SimpleNamespace(audit_log_path=runtime_root / "audit.jsonl")
                with (
                    patch("nasdaq_auto_trader.app_ui.application_data_root", return_value=runtime_root),
                    patch(
                        "nasdaq_auto_trader.app_ui.default_strategy_artifact_paths",
                        return_value=artifacts,
                    ),
                ):
                    app = DashboardApp(
                        root,
                        controller,
                        tk_module=tk,
                        ttk_module=ttk,
                        messagebox_module=Mock(),
                        config_path=runtime_root / "config.kis.json",
                        portfolio_refresh_seconds=3600,
                    )
                app._daily_report_service = FixtureReportService(report_path)
                self.assertFalse(hasattr(app, "settings_button"))
                self._pump_until_idle(root, app)
                self._pump_until(
                    root,
                    lambda: app.start_button.instate(["!disabled"]),
                )

                app.start_button.invoke()
                self._pump_until_idle(root, app)
                self.assertEqual(controller.state, "running")
                self.assertNotEqual(app.status_var.get(), "요청 처리 중")

                controller.run_operating_cycle = Mock(return_value=[])
                app._result_queue.put(
                    (
                        "ok",
                        "portfolio",
                        PortfolioSnapshot(
                            as_of=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
                            mode="dry_run",
                            broker="dry_run",
                            account=AccountSnapshot(0, 27.18, 0),
                            positions=[
                                PositionRow(
                                    "WBD",
                                    1,
                                    25.795,
                                    27.18,
                                    27.18,
                                    1.385,
                                    5.3693,
                                )
                            ],
                        ),
                    )
                )
                self._pump_until(
                    root,
                    lambda: controller.run_operating_cycle.called,
                )
                self._pump_until_idle(root, app)
                controller.run_operating_cycle.assert_called_once_with(force=True)
                self.assertIn(
                    "익절 기준 감지: 즉시 매도 조건 재평가",
                    app.log_text.get("1.0", "end"),
                )

                self._pump_until(
                    root,
                    lambda: app.learning_button.instate(["!disabled"]),
                )
                app.learning_button.invoke()
                self._pump_until_idle(root, app)
                visible_log = app.log_text.get("1.0", "end")
                self.assertIn("자동매매 실행", visible_log)
                self.assertIn("학습만 실행", visible_log)
                self.assertIn("제출된 실제 주문: 0건", visible_log)

                with patch(
                    "nasdaq_auto_trader.app_ui_actions.webbrowser.open",
                    return_value=True,
                ) as open_report:
                    self._pump_until(
                        root,
                        lambda: app.report_button.instate(["!disabled"]),
                    )
                    app.report_button.invoke()
                open_report.assert_called_once_with(report_path.resolve().as_uri())

                controller.refresh_portfolio = Mock(side_effect=OSError("network offline"))
                self._pump_until(
                    root,
                    lambda: app.refresh_button.instate(["!disabled"]),
                )
                app.refresh_button.invoke()
                self._pump_until_idle(root, app)
                visible_log = app.log_text.get("1.0", "end")
                self.assertEqual(app.status_var.get(), "보유현황 조회 재시도 예약")
                self.assertIn("network offline", visible_log)
                self.assertIn("자동 재시도", visible_log)
        finally:
            root.destroy()

    @staticmethod
    def _pump_until_idle(root, app: DashboardApp) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            root.update()
            if app._worker is None and app._result_queue.empty():
                root.update()
                return
            time.sleep(0.01)
        raise AssertionError("GUI worker did not become idle within 5 seconds")

    @staticmethod
    def _pump_until(root, predicate) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            root.update()
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError("GUI condition was not met within 5 seconds")


if __name__ == "__main__":
    unittest.main()
