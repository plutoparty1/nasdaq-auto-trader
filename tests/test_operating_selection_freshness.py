from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

from nasdaq_auto_trader.app_controller import AutoTradeController
from nasdaq_auto_trader.app_types import EngineResult
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.engine_errors import PreOrderCycleError
from nasdaq_auto_trader.market_hours import latest_completed_market_date
from nasdaq_auto_trader.operating_state import OperatingState
from nasdaq_auto_trader.quant_data.symbol_selector import SelectionReport
from tests.app_controller_fixtures import IsolatedControllerTestCase


class OperatingSelectionFreshnessTests(IsolatedControllerTestCase):
    def controller_at(self, now: datetime) -> AutoTradeController:
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]), clock=lambda: now,
        )
        controller.operating_store.save(replace(
            controller.operating_store.load(),
            last_learning_market_date=latest_completed_market_date(now),
        ))
        controller.start(interval_seconds=60)
        controller.last_selection_report = SelectionReport(
            status="selected", universe_id="nasdaq-100",
            universe_effective_date="2026-09-18", strategy_id="learned",
            strategy_version="v1", strategy_digest="digest", shortlist_count=1,
            ranked=(), selected_symbols=("WBD",),
        )
        return controller

    def test_idle_cycle_clears_previous_selection(self) -> None:
        # Given: Sunday's idle cycle follows an earlier selected report.
        controller = self.controller_at(datetime(2026, 9, 20, 14, tzinfo=timezone.utc))
        # When: no new trading evaluation runs.
        result = controller.run_operating_cycle(force=True)
        # Then: the idle cycle cannot publish the earlier selection as current.
        self.assertEqual(result, [])
        self.assertIs(controller.operating_store.load().state, OperatingState.IDLE)
        self.assertIsNone(controller.last_selection_report)

    def test_preflight_failure_clears_previous_selection(self) -> None:
        # Given: a prior selection exists before preflight fails.
        controller = self.controller_at(datetime(2026, 9, 18, 14, tzinfo=timezone.utc))
        # When: the cycle stops before trading.
        with patch.object(controller, "_operating_health", side_effect=PreOrderCycleError("market_data_unavailable")):
            result = controller.run_operating_cycle(force=True)
        # Then: no previous selection remains attached to the failed cycle.
        self.assertEqual(result, [])
        self.assertIsNone(controller.last_selection_report)

    def test_live_cycle_retains_new_selection(self) -> None:
        # Given: a trading cycle will produce a fresh report without broker calls.
        controller = self.controller_at(datetime(2026, 9, 18, 14, tzinfo=timezone.utc))
        previous = controller.last_selection_report
        assert previous is not None
        fresh = replace(previous, selected_symbols=("QQQ",))

        def run_cycle(force: bool = False) -> list[EngineResult]:
            controller.last_selection_report = fresh
            return []

        # When: the regular-session branch executes the trading cycle.
        with patch.object(controller, "run_auto_cycle", side_effect=run_cycle):
            controller.run_operating_cycle(force=True)
        # Then: the new report remains available to consumers.
        self.assertIs(controller.operating_store.load().state, OperatingState.LIVE_TRADING)
        self.assertIs(controller.last_selection_report, fresh)
