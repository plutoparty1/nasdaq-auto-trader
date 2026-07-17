import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from nasdaq_auto_trader.app_ui_render import DashboardRenderMixin
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.test_gui_auto_start_feedback import PositionsTree, Variable
from tests.app_controller_fixtures import IsolatedControllerTestCase


class GuiRecoverableFeedbackTests(IsolatedControllerTestCase):
    def test_running_safe_retry_is_visible_after_auto_cycle(self):
        view = DashboardRenderMixin()
        view.controller = SimpleNamespace(
            state="running",
            last_error="market_data_unavailable",
            selection_error=None,
            last_selection_report=None,
            last_shadow_scan=None,
            trading_settings=TradingSettings(unattended_operation_enabled=True),
        )
        view.status_var = Variable()
        logs: list[str] = []
        view._append_log = logs.append

        view._render_auto_results([])

        expected = "자동운영 재시도 예약: 시장 데이터 연결을 확인할 수 없음"
        self.assertEqual(view.status_var.value, expected)
        self.assertEqual(logs, [expected])

    def test_portfolio_refresh_preserves_running_safe_retry_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                engine_factory=lambda config: SimpleNamespace(
                    load_portfolio=lambda refresh=False: (
                        AccountSnapshot(cash=64.83, equity=64.83, buying_power=64.83),
                        {},
                    )
                ),
                trading_settings=TradingSettings(unattended_operation_enabled=True),
                session_store=TradingSessionStore(Path(temp_dir) / "session.json"),
            )
            controller.start()
            controller.last_error = "market_data_unavailable"

            snapshot = controller.refresh_portfolio()

            view = DashboardRenderMixin()
            view.controller = controller
            view.status_var = Variable()
            view.cash_var = Variable()
            view.equity_var = Variable()
            view.buying_power_var = Variable()
            view.updated_var = Variable()
            view.positions_tree = PositionsTree()
            view._render_snapshot(snapshot)

        self.assertEqual(controller.last_error, "market_data_unavailable")
        self.assertIn("자동운영 재시도 예약", view.status_var.value)


if __name__ == "__main__":
    unittest.main()
