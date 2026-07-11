import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from nasdaq_auto_trader.app_controller import AutoTradeController
from nasdaq_auto_trader.app_ui_render import DashboardRenderMixin
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import SettingsError, TradingSettings
from nasdaq_auto_trader.config_manager import validate_order_against_settings
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest
from nasdaq_auto_trader.quant_data.symbol_selector import SelectionReport
from nasdaq_auto_trader.settings_window_dialog import SettingsWindow
from nasdaq_auto_trader.trading_session_store import TradingSessionStore


class AutoSymbolGuiTests(unittest.TestCase):
    def test_auto_toggle_disables_only_manual_symbol_inputs(self):
        window = SettingsWindow.__new__(SettingsWindow)
        auto = _Variable(False)
        window.variables = {"auto_symbol_selection_enabled": auto}
        window.widgets = {
            "ticker": _Widget(),
            "ai_candidate_tickers": _Widget(),
            "order_qty": _Widget(),
        }

        window._sync_auto_symbol_widgets()
        auto.set(True)
        window._sync_auto_symbol_widgets()

        self.assertEqual(window.widgets["ticker"].state, "disabled")
        self.assertEqual(window.widgets["ai_candidate_tickers"].state, "disabled")
        self.assertEqual(window.widgets["order_qty"].state, "normal")

        auto.set(False)
        window._sync_auto_symbol_widgets()
        self.assertEqual(window.widgets["ticker"].state, "normal")
        self.assertEqual(window.widgets["ai_candidate_tickers"].state, "normal")

    def test_enabling_auto_mode_replaces_stale_manual_selection_summary(self):
        view = DashboardRenderMixin()
        view.controller = SimpleNamespace(
            config=AppConfig(),
            trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
            settings_path=Path("trading.json"),
            last_selection_report=None,
        )
        view.config_path = "config.json"
        view.warning_var = _Variable("")
        view.selection_var = _Variable("수동 종목 모드 | QQQ")
        view.mode_var = _Variable("")
        view._append_log = lambda message: None

        view._render_mode()

        self.assertEqual(view.selection_var.get(), "자동 종목 선택 | 다음 주기 대기")

    def test_gui_live_action_blocks_before_engine_factory(self):
        factory = _SequenceFactory([_report("selected")])
        controller = AutoTradeController(
            AppConfig(),
            engine_factory=factory,
            trading_settings=TradingSettings(
                auto_symbol_selection_enabled=True,
                dry_run=False,
                live_trading=True,
            ),
        )

        with self.assertRaisesRegex(SettingsError, "gui_live_trading_disabled"):
            controller.start()
        with self.assertRaisesRegex(SettingsError, "gui_live_trading_disabled"):
            controller.refresh_portfolio()

        self.assertEqual(factory.calls, 0)

    def test_gui_auto_dry_run_and_paper_reach_controller(self):
        for settings in (
            TradingSettings(auto_symbol_selection_enabled=True),
            TradingSettings(
                auto_symbol_selection_enabled=True,
                dry_run=False,
                live_trading=False,
            ),
        ):
            with self.subTest(mode="dry_run" if settings.dry_run else "paper"):
                with tempfile.TemporaryDirectory() as temp_dir:
                    factory = _SequenceFactory([_report("selected")])
                    controller = AutoTradeController(
                        AppConfig(),
                        engine_factory=factory,
                        trading_settings=settings,
                        session_store=TradingSessionStore(
                            Path(temp_dir) / "session.json"
                        ),
                    )
                    controller.start()
                    result = controller.run_auto_cycle(force=True)

                self.assertEqual(result, [])
                self.assertEqual(factory.calls, 1)
                self.assertEqual(controller.last_selection_report.status, "selected")

    def test_corrupt_session_store_remains_blocked_after_settings_update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            path.write_text("{broken", encoding="utf-8")
            factory = _SequenceFactory([_report("selected")])
            controller = AutoTradeController(
                AppConfig(),
                engine_factory=factory,
                trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
                session_store=TradingSessionStore(path),
            )

            controller.update_settings(
                TradingSettings(auto_symbol_selection_enabled=True)
            )
            with self.assertRaisesRegex(SettingsError, "session_store_corrupt"):
                controller.start()

        self.assertEqual(factory.calls, 0)

    def test_three_blocks_persist_error_until_selected_but_no_trade_is_normal(self):
        factory = _SequenceFactory(
            [
                _report("blocked"),
                _report("no_trade"),
                _report("blocked"),
                _report("blocked"),
                _report("no_trade"),
                _report("selected"),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = AutoTradeController(
                AppConfig(),
                engine_factory=factory,
                trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
                session_store=TradingSessionStore(Path(temp_dir) / "session.json"),
            )
            controller.start()

            controller.run_auto_cycle(force=True)
            controller.run_auto_cycle(force=True)
            self.assertEqual(controller.automatic_block_streak, 1)
            controller.run_auto_cycle(force=True)
            controller.run_auto_cycle(force=True)
            self.assertIsNotNone(controller.selection_error)
            controller.run_auto_cycle(force=True)
            self.assertIsNotNone(controller.selection_error)
            self.assertEqual(controller.state, "running")
            controller.run_auto_cycle(force=True)

        self.assertEqual(controller.automatic_block_streak, 0)
        self.assertIsNone(controller.selection_error)

    def test_paper_safety_counts_and_cooldown_survive_controller_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
            settings = TradingSettings(
                auto_symbol_selection_enabled=True,
                cooldown_enabled=True,
                cooldown_minutes=10,
                max_daily_buy_count=10,
            )
            first = AutoTradeController(
                AppConfig(),
                engine_factory=_RecordingFactory(now),
                clock=lambda: now,
                trading_settings=settings,
                session_store=store,
            )
            first.start()
            first.run_auto_cycle(force=True)

            second = AutoTradeController(
                AppConfig(),
                engine_factory=_SequenceFactory([_report("no_trade")]),
                clock=lambda: now,
                trading_settings=settings,
                session_store=store,
            )

            response = validate_order_against_settings(
                OrderRequest("QQQ", "buy", qty=1),
                AccountSnapshot(10_000, 10_000, 10_000),
                None,
                settings,
                second.session_state,
                now,
                "paper",
            )

        self.assertEqual(second.session_state.buy_count, 1)
        self.assertEqual(second.session_state.last_order_at, now)
        self.assertEqual(response["reason"], "cooldown_active")


class _Variable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Widget:
    def __init__(self):
        self.state = "normal"

    def configure(self, **kwargs):
        self.state = kwargs["state"]


class _Engine:
    def __init__(self, report, state=None, now=None):
        self.last_selection_report = report
        self.state = state
        self.now = now

    def run_once(self):
        if self.state is not None and self.now is not None:
            self.state.record_order("buy", self.now)
        return []

    def load_portfolio(self, refresh=False):
        raise AssertionError("portfolio should not be loaded")


class _SequenceFactory:
    def __init__(self, reports):
        self.reports = list(reports)
        self.calls = 0

    def __call__(self, config, **kwargs):
        del config, kwargs
        report = self.reports[min(self.calls, len(self.reports) - 1)]
        self.calls += 1
        return _Engine(report)


class _RecordingFactory:
    def __init__(self, now):
        self.now = now

    def __call__(self, config, **kwargs):
        del config
        return _Engine(
            _report("selected"),
            kwargs["trading_session_state"],
            self.now,
        )


def _report(status: str) -> SelectionReport:
    return SelectionReport(
        status=status,
        universe_id="nasdaq_100",
        universe_effective_date="2026-07-10",
        strategy_id="learned",
        strategy_version="v1",
        strategy_digest="digest",
        shortlist_count=1,
        ranked=(),
        selected_symbols=("QQQ",) if status == "selected" else (),
        blocked_reasons=("market_data_incomplete",) if status == "blocked" else (),
    )


if __name__ == "__main__":
    unittest.main()
