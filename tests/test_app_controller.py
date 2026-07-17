import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.learning_runner import LearningCancellation, LearningRunResult
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.intraday_shadow_scan import IntradayShadowScanReport
from nasdaq_auto_trader.quant_data.symbol_selector import StrategyResolutionBlock
from nasdaq_auto_trader.operating_state import OperatingState, OperatingStateStore, RuntimeState
from tests.app_controller_fixtures import FakeEngineFactory, IsolatedControllerTestCase


class AppControllerTests(IsolatedControllerTestCase):
    def test_open_market_missing_strategy_runs_shadow_scan_without_pausing(self):
        now = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=FakeEngineFactory(),
            clock=lambda: now,
            trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
            session_store=self.session_store(),
        )
        expected = IntradayShadowScanReport(
            now,
            "nasdaq-100",
            ("AAPL",),
            ("AAPL",),
            {},
            False,
            Path("scan.json"),
        )
        controller.start()

        with (
            patch(
                "nasdaq_auto_trader.controller_operations.resolve_strategy",
                return_value=StrategyResolutionBlock("eligible_strategy_unavailable"),
            ),
            patch(
                "nasdaq_auto_trader.controller_operations.run_intraday_shadow_scan",
                return_value=expected,
            ) as scan,
        ):
            controller.run_operating_cycle(force=True)

        self.assertEqual(controller.state, "running")
        self.assertEqual(controller.last_shadow_scan, expected)
        self.assertEqual(scan.call_count, 1)
        self.assertFalse(hasattr(scan.call_args.args[1], "submit_order"))

    def test_completed_learning_runs_once_per_completed_market_date(self):
        now = datetime(2026, 6, 26, 21, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OperatingStateStore(Path(temp_dir) / "operating.json")
            store.save(
                RuntimeState(
                    OperatingState.IDLE,
                    now,
                    last_reconciled_market_date="2026-06-26",
                )
            )
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                engine_factory=FakeEngineFactory(),
                clock=lambda: now,
                session_store=self.session_store(),
                operating_store=store,
            )
            controller.start()
            completed = LearningRunResult(
                "completed", 1, 0, ("strategy_rejected",), 0, Path(temp_dir)
            )

            with patch.object(
                controller,
                "_execute_learning",
                return_value=completed,
            ) as learning:
                controller.run_operating_cycle(force=True)
                controller.run_operating_cycle(force=True)

            state = store.load()

        self.assertEqual(learning.call_count, 1)
        self.assertEqual(state.last_learning_market_date, "2026-06-26")

    def test_completed_manual_learning_marks_market_date(self):
        now = datetime(2026, 6, 26, 21, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self.operating_store()
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                clock=lambda: now,
                session_store=self.session_store(),
                operating_store=store,
            )
            completed = LearningRunResult(
                "completed", 1, 0, (), 0, Path(temp_dir)
            )

            with patch.object(
                controller,
                "_execute_learning",
                return_value=completed,
            ):
                controller.run_learning_only()

            state = store.load()

        self.assertEqual(state.last_learning_market_date, "2026-06-26")

    def test_live_trading_cycle_clears_previous_shadow_scan_feedback(self):
        now = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=FakeEngineFactory(),
            clock=lambda: now,
            session_store=self.session_store(),
        )
        controller.last_shadow_scan = IntradayShadowScanReport(
            now, "nasdaq-100", ("AAPL",), ("AAPL",), {}, False, Path("scan.json")
        )
        controller.start()

        controller.run_operating_cycle(force=True)

        self.assertIsNone(controller.last_shadow_scan)
    def test_manual_symbol_mode_does_not_require_a_learned_model(self):
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=FakeEngineFactory(),
            session_store=self.session_store(),
        )

        health = controller._operating_health()

        self.assertTrue(health.model_ok)

    def test_manual_learning_persists_train_only_state_and_returns_to_idle(self):
        observed_states = []
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                session_store=self.session_store(),
                operating_store=OperatingStateStore(Path(temp_dir) / "operating.json"),
            )
            cancellation = LearningCancellation(
                lambda progress: observed_states.append(
                    controller.operating_store.load().state
                )
            )

            result = controller.run_learning_only(cancellation)
            final_state = controller.operating_store.load().state

        self.assertEqual(result.status, "blocked")
        self.assertIn(OperatingState.MANUAL_TRAIN_ONLY, observed_states)
        self.assertEqual(final_state, OperatingState.IDLE)

if __name__ == "__main__":
    unittest.main()
