import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.app import AutoTradeController
from nasdaq_auto_trader.automation_coordinator import AutomationCoordinator
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position
from nasdaq_auto_trader.operating_state import OperatingStateStore
from nasdaq_auto_trader.trading_session_store import TradingSessionStore


class IsolatedControllerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._controller_runtime = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._controller_runtime.cleanup()
        super().tearDown()

    def operating_store(self) -> OperatingStateStore:
        return OperatingStateStore(
            Path(self._controller_runtime.name) / "operating-state.json"
        )

    def session_store(self) -> TradingSessionStore:
        return TradingSessionStore(
            Path(self._controller_runtime.name) / "trading-session.json"
        )

    def create_controller(self, config: AppConfig, **kwargs) -> AutoTradeController:
        operating_store = kwargs.pop("operating_store", self.operating_store())
        kwargs.setdefault("session_store", self.session_store())
        controller = AutoTradeController(config, **kwargs)
        controller.operating_store = operating_store
        controller.operating_coordinator = AutomationCoordinator(operating_store)
        return controller


class FakeEngine:
    def __init__(self):
        self.run_count = 0
        self.refresh_flags = []
        self.market_data = StaticMarketData()

    def run_once(self):
        self.run_count += 1
        return [
            {
                "symbol": "QQQ",
                "decision": None,
                "order": None,
                "response": {"status": "fake"},
                "account": AccountSnapshot(cash=100, equity=120, buying_power=80),
                "buying_power_check": None,
                "trading_agents": None,
            }
        ]

    def load_portfolio(self, refresh=False):
        self.refresh_flags.append(refresh)
        return (
            AccountSnapshot(cash=100, equity=120, buying_power=80),
            {
                "QQQ": Position(
                    symbol="QQQ",
                    qty=2,
                    market_value=120,
                    avg_entry_price=50,
                )
            },
        )


class FakeEngineFactory:
    def __init__(self):
        self.instances = []

    def __call__(self, config):
        del config
        engine = FakeEngine()
        self.instances.append(engine)
        return engine


class FailingReconciliationEngine(FakeEngine):
    def load_portfolio(self, refresh=False):
        del refresh
        raise OSError("broker unavailable")


class FailingReconciliationFactory:
    def __call__(self, config):
        del config
        return FailingReconciliationEngine()


class RefreshBroker:
    def __init__(self):
        self.account_refresh = None
        self.positions_refresh = None

    def submit_order(self, order):
        del order
        return {"status": "unused"}

    def get_account(self, refresh=False):
        self.account_refresh = refresh
        return AccountSnapshot(cash=10, equity=11, buying_power=9)

    def list_positions(self, refresh=False):
        self.positions_refresh = refresh
        return {
            "QQQ": Position(
                symbol="QQQ",
                qty=1,
                market_value=11,
                avg_entry_price=10,
            )
        }


class StaticMarketData:
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        del timeframe, start, end, limit
        return {
            symbol: [
                Bar(
                    symbol=symbol,
                    timestamp="T001",
                    open=10,
                    high=11,
                    low=9,
                    close=10,
                    volume=1000,
                )
            ]
            for symbol in symbols
        }
