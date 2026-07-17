import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, sentinel

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.operating_state import OperatingState, OperatingStateStore, RuntimeState
from tests.app_controller_fixtures import (
    FailingReconciliationFactory,
    FakeEngineFactory,
    IsolatedControllerTestCase,
    RefreshBroker,
    StaticMarketData,
)


class AppControllerReconciliationTests(IsolatedControllerTestCase):
    def test_post_market_cycle_reconciles_account_before_learning(self):
        factory = FakeEngineFactory()
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                engine_factory=factory,
                clock=lambda: datetime(2026, 6, 26, 21, 0, tzinfo=timezone.utc),
                session_store=self.session_store(),
                operating_store=OperatingStateStore(Path(temp_dir) / "operating.json"),
            )
            controller.start()

            with patch(
                "nasdaq_auto_trader.controller_operations.resolve_strategy",
                return_value=sentinel.strategy,
            ):
                controller.run_operating_cycle(force=True)

            state = controller.operating_store.load()

        self.assertEqual(state.state, OperatingState.POST_MARKET_RECONCILIATION)
        self.assertEqual(state.last_reconciled_market_date, "2026-06-26")
        self.assertEqual(factory.instances[0].refresh_flags, [True])

    def test_restart_retries_post_market_reconciliation_without_success_marker(self):
        factory = FakeEngineFactory()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OperatingStateStore(Path(temp_dir) / "operating.json")
            store.save(
                RuntimeState(
                    OperatingState.POST_MARKET_RECONCILIATION,
                    datetime(2026, 6, 26, 21, 0, tzinfo=timezone.utc),
                )
            )
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                engine_factory=factory,
                clock=lambda: datetime(2026, 6, 26, 21, 0, tzinfo=timezone.utc),
                session_store=self.session_store(),
                operating_store=store,
            )
            controller.start()

            controller.run_operating_cycle(force=True)

        self.assertEqual(factory.instances[0].refresh_flags, [True])

    def test_post_market_reconciliation_failure_enters_safe_halt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                engine_factory=FailingReconciliationFactory(),
                clock=lambda: datetime(2026, 6, 26, 21, 0, tzinfo=timezone.utc),
                session_store=self.session_store(),
                operating_store=OperatingStateStore(Path(temp_dir) / "operating.json"),
            )
            controller.start()

            controller.run_operating_cycle(force=True)

            state = controller.operating_store.load()

        self.assertEqual(state.state, OperatingState.SAFE_HALT)
        self.assertEqual(controller.state, "paused")
        self.assertIn("account_state_unavailable", controller.last_error)

    def test_refresh_portfolio_builds_rows_from_latest_broker_state(self):
        factory = FakeEngineFactory()
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=factory,
            clock=lambda: datetime(2026, 6, 30, 1, 2, tzinfo=timezone.utc),
            session_store=self.session_store(),
        )

        snapshot = controller.refresh_portfolio()

        self.assertEqual(snapshot.account.cash, 100)
        self.assertEqual(snapshot.positions[0].symbol, "QQQ")
        self.assertEqual(snapshot.positions[0].latest_price, 60)
        self.assertEqual(snapshot.positions[0].unrealized_pl, 20)
        self.assertEqual(snapshot.positions[0].unrealized_pl_pct, 20)
        self.assertEqual(factory.instances[0].refresh_flags, [True])

    def test_start_pause_and_resume_gate_auto_cycles(self):
        factory = FakeEngineFactory()
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=factory,
            clock=lambda: datetime(2026, 6, 30, 1, 2, tzinfo=timezone.utc),
            session_store=self.session_store(),
        )

        controller.start(interval_seconds=60)
        first_result = controller.run_auto_cycle(force=True)
        controller.pause()
        paused_result = controller.run_auto_cycle(force=True)
        controller.resume()
        resumed_result = controller.run_auto_cycle(force=True)

        self.assertEqual(controller.state, "running")
        self.assertEqual(len(first_result), 1)
        self.assertIsNone(paused_result)
        self.assertEqual(len(resumed_result), 1)
        self.assertEqual(len(factory.instances), 2)

    def test_trading_engine_load_portfolio_passes_refresh_to_broker(self):
        broker = RefreshBroker()
        engine = TradingEngine(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            broker=broker,
            market_data=StaticMarketData(),
        )

        account, positions = engine.load_portfolio(refresh=True)

        self.assertEqual(account.cash, 10)
        self.assertEqual(positions["QQQ"].market_value, 11)
        self.assertTrue(broker.account_refresh)
        self.assertTrue(broker.positions_refresh)


if __name__ == "__main__":
    unittest.main()
