import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.engine_errors import PreOrderCycleError
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.operating_state import OperatingState, OperatingStateStore
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.app_controller_fixtures import IsolatedControllerTestCase


class OfflineMarketData:
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        del symbols, timeframe, start, end, limit
        raise OSError("market data offline")


class PreOrderFailingFactory:
    def __call__(self, config, **kwargs):
        del config, kwargs

        def fail():
            raise PreOrderCycleError("market_data_unavailable")

        return SimpleNamespace(run_once=fail)


class PreOrderCycleFailureTests(IsolatedControllerTestCase):
    def test_engine_classifies_market_data_failure_before_order_boundary(self):
        engine = TradingEngine(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            market_data=OfflineMarketData(),
            account=AccountSnapshot(cash=64.83, equity=64.83, buying_power=64.83),
            positions={},
        )

        with self.assertRaises(PreOrderCycleError) as raised:
            engine.run_once()

        self.assertEqual(raised.exception.reason, "market_data_unavailable")

    def test_regular_session_preorder_outage_schedules_safe_retry(self):
        now = datetime(2026, 7, 17, 14, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                engine_factory=PreOrderFailingFactory(),
                clock=lambda: now,
                interval_seconds=15 * 60,
                trading_settings=TradingSettings(unattended_operation_enabled=True),
                session_store=TradingSessionStore(root / "session.json"),
                operating_store=OperatingStateStore(root / "operating.json"),
            )
            controller.start()

            result = controller.run_operating_cycle(force=True)
            runtime_state = controller.operating_store.load()

        self.assertEqual(result, [])
        self.assertEqual(controller.state, "running")
        self.assertEqual(controller.last_error, "market_data_unavailable")
        self.assertEqual(controller.next_run_at, now + timedelta(minutes=15))
        self.assertEqual(runtime_state.state, OperatingState.SAFE_HALT)


if __name__ == "__main__":
    unittest.main()
