import queue
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nasdaq_auto_trader.app_ui_actions import DashboardActionsMixin
from nasdaq_auto_trader.app_ui_render import DashboardRenderMixin
from nasdaq_auto_trader.app_types import PortfolioSnapshot, PositionRow
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.test_gui_auto_start_feedback import PositionsTree, Variable
from tests.app_controller_fixtures import IsolatedControllerTestCase


class GuiRecoverableFeedbackTests(IsolatedControllerTestCase):
    def test_portfolio_profit_below_threshold_keeps_five_minute_schedule(self):
        # Given WBD is still below the exact configured 5% take-profit threshold.
        view = DashboardActionsMixin()
        view.controller = SimpleNamespace(
            state="running",
            trading_settings=TradingSettings(take_profit_rate=5.0),
        )
        view._result_queue = queue.Queue()
        view._result_queue.put(
            (
                "ok",
                "portfolio",
                SimpleNamespace(
                    positions=[
                        SimpleNamespace(symbol="WBD", unrealized_pl_pct=4.9622)
                    ]
                ),
            )
        )
        view._worker = object()
        view._take_profit_symbols = set()
        view.portfolio_refresh_seconds = 15.0
        view._render_snapshot = Mock()
        view._update_controls = Mock()
        view._start_task = Mock(return_value=True)
        view.root = SimpleNamespace(after=lambda *_args: None)

        # When the 15-second portfolio result is handled.
        view._poll_results()

        # Then no accelerated trading cycle is started.
        view._start_task.assert_not_called()

    def test_five_percent_portfolio_profit_triggers_once_per_crossing(self):
        # Given a running unattended view whose 15-second portfolio refresh sees +5%.
        controller = SimpleNamespace(
            state="running",
            trading_settings=TradingSettings(take_profit_rate=5.0),
            run_operating_cycle=Mock(return_value=[]),
        )
        snapshot = PortfolioSnapshot(
            as_of=datetime(2026, 8, 11, 0, 9, tzinfo=timezone.utc),
            mode="live",
            broker="kis",
            account=AccountSnapshot(cash=0, equity=27.18, buying_power=0),
            positions=[
                PositionRow(
                    symbol="WBD",
                    qty=1,
                    avg_entry_price=25.795,
                    market_value=27.18,
                    latest_price=27.18,
                    unrealized_pl=1.385,
                    unrealized_pl_pct=5.3693,
                )
            ],
        )
        view = DashboardActionsMixin()
        view.controller = controller
        view._result_queue = queue.Queue()
        view._result_queue.put(("ok", "portfolio", snapshot))
        view._result_queue.put(("ok", "portfolio", snapshot))
        view._worker = object()
        view._take_profit_symbols = set()
        view.portfolio_refresh_seconds = 15.0
        view._next_portfolio_refresh = 0.0
        view.root = SimpleNamespace(after=lambda *_args: None)
        view._render_snapshot = Mock()
        view._update_controls = Mock()
        view._append_log = Mock()
        view._start_task = Mock(return_value=True)

        # When the portfolio result is handled.
        with patch(
            "nasdaq_auto_trader.app_ui_actions.time.monotonic",
            return_value=100.0,
        ):
            view._poll_results()

        view._result_queue.put(
            ("ok", "portfolio", SimpleNamespace(positions=[]))
        )
        view._poll_results()
        view._result_queue.put(("ok", "portfolio", snapshot))
        view._poll_results()

        # Then the guarded operating cycle is pulled forward immediately.
        self.assertEqual(view._start_task.call_count, 2)
        for call in view._start_task.call_args_list:
            label, task = call.args
            self.assertEqual(label, "auto")
            task()
        self.assertEqual(controller.run_operating_cycle.call_count, 2)
        controller.run_operating_cycle.assert_called_with(force=True)

    def test_failed_immediate_start_retries_while_profit_stays_above_threshold(self):
        view = DashboardActionsMixin()
        view.controller = SimpleNamespace(
            state="running",
            trading_settings=TradingSettings(take_profit_rate=5.0),
        )
        snapshot = SimpleNamespace(
            positions=[SimpleNamespace(symbol="WBD", unrealized_pl_pct=5.1)]
        )
        view._result_queue = queue.Queue()
        view._result_queue.put(("ok", "portfolio", snapshot))
        view._worker = object()
        view._take_profit_symbols = set()
        view.portfolio_refresh_seconds = 15.0
        view.root = SimpleNamespace(after=lambda *_args: None)
        view._render_snapshot = Mock()
        view._update_controls = Mock()
        view._append_log = Mock()
        view._start_task = Mock(side_effect=[False, True])

        view._poll_results()
        view._result_queue.put(("ok", "portfolio", snapshot))
        view._poll_results()

        self.assertEqual(view._start_task.call_count, 2)
        view._append_log.assert_called_once_with(
            "익절 기준 감지: 즉시 매도 조건 재평가"
        )

    def test_portfolio_timeout_is_shown_as_scheduled_retry(self):
        view = DashboardActionsMixin()
        view._result_queue = queue.Queue()
        view._result_queue.put(
            (
                "error",
                "portfolio",
                ("KIS GET reconciliation deadline exceeded", "traceback details"),
            )
        )
        view._worker = object()
        view.status_var = Variable()
        view.portfolio_refresh_seconds = 15.0
        view._next_portfolio_refresh = 0.0
        view.root = SimpleNamespace(after=lambda *_args: None)
        view._update_controls = lambda: None
        logs: list[str] = []
        view._append_log = logs.append

        with patch(
            "nasdaq_auto_trader.app_ui_actions.time.monotonic",
            return_value=100.0,
        ):
            view._poll_results()

        self.assertEqual(view.status_var.value, "보유현황 조회 재시도 예약")
        self.assertEqual(view._next_portfolio_refresh, 115.0)
        self.assertEqual(
            logs[0],
            "보유현황 조회 실패, 15초 후 자동 재시도: "
            "KIS GET reconciliation deadline exceeded",
        )
        self.assertEqual(logs[1], "traceback details")

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
