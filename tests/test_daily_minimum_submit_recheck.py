from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Literal

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position
from nasdaq_auto_trader.risk import RiskConfig, RiskManager
from nasdaq_auto_trader.session_claims import ClaimStatus
from nasdaq_auto_trader.session_store_io import read_session_payload
from tests.auto_symbol_live_guard_fixtures import (
    _live_engine,
    _LiveBroker,
    _write_champion,
)
from tests.test_auto_symbol_engine import AUTO_TEST_NOW, _guard, _write_paper_strategy
from tests.test_automatic_entry_eligibility import price_bars
from tests.test_daily_buy_objective import History


class HistoryChangingBroker(_LiveBroker):
    def __init__(self, history: tuple[History, ...], error: bool = False) -> None:
        super().__init__("accepted")
        self.history = history
        self.error = error
        self.history_calls = 0
        self.on_final_history: Callable[[], None] | None = None

    def list_order_history(self, start_date: str, end_date: str) -> tuple[History, ...]:
        self.history_calls += 1
        if self.history_calls == 1:
            return ()
        if self.on_final_history is not None:
            self.on_final_history()
        if self.error:
            raise BrokerRequestError("history_temporarily_unavailable")
        return self.history


class AffordableMarket:
    def get_stock_bars(
        self, symbols: list[str], timeframe: str, start: str,
        end: str | None = None, limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        bars = [
            replace(bar, high=bar.close + .3, low=bar.close - .3)
            for bar in price_bars("WBD", [1 + index * .005 for index in range(220)])
        ]
        return {"WBD": bars} if "WBD" in symbols else {}

    def get_latest_quotes(self, symbols: list[str]) -> dict[str, JsonObject]:
        return {symbol: {"bp": 2.095, "ap": 2.1} for symbol in symbols}

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        return AccountSnapshot(63.09, 63.09, 63.09)

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        return {}

    def get_overseas_buying_power(self, symbol: str, price: float) -> float:
        return 63.09


def make_engine(tmp_path: Path, broker: HistoryChangingBroker) -> TradingEngine:
    paths = StrategyArtifactPaths.from_root(tmp_path / "artifacts")
    _write_champion(paths, threshold=.99)
    engine = _live_engine(
        paths, _guard(paths, tmp_path), broker, issue_authorization=False,
        daily_forced=True, market_data=AffordableMarket(),
    )
    engine.config = replace(engine.config, risk=RiskConfig(order_qty=1, max_position_pct=.5))
    engine.risk_manager = RiskManager(engine.config.risk)
    engine.trading_settings = replace(engine.trading_settings, daily_minimum_buy_enabled=True)
    return engine


@pytest.mark.parametrize("history,reason", [
    ((History(symbol="OTHER", submitted_at=AUTO_TEST_NOW),), "daily_minimum_objective_changed"),
    ((History(filled_quantity=0, status="new", submitted_at=AUTO_TEST_NOW),),
     "daily_minimum_history_unresolved"),
    ((History(submitted_at=None),), "daily_minimum_history_invalid"),
])
def test_daily_exception_stops_when_history_changes_before_submission(
    tmp_path: Path, history: tuple[History, ...], reason: str,
) -> None:
    # Given: a first-share candidate whose risk exceeds the ordinary one-percent cap.
    broker = HistoryChangingBroker(history)
    engine = make_engine(tmp_path, broker)
    # When: broker history changes after the initial daily-objective query.
    results = engine.run_once()
    # Then: the exception is withdrawn before any broker submission.
    assert broker.orders == []
    assert results[0]["decision"].risk_per_share > 63.09 * .01
    assert results[0]["response"]["reason"] == reason
    assert broker.history_calls == 2
    assert engine.automatic_order_guard.session_store.load_buy_receipts() == ()
    _, claims = read_session_payload(engine.automatic_order_guard.session_store.path)
    assert [claim.status for claim in claims.values()] == [ClaimStatus.REJECTED]
    assert engine.trading_session_state.buy_count == 0


def test_daily_history_recheck_cannot_bypass_authorization_revoked_during_fetch(tmp_path: Path) -> None:
    broker = HistoryChangingBroker(())
    engine = make_engine(tmp_path, broker)

    def revoke() -> None:
        engine.automatic_order_guard.authorization_store.clear()

    broker.on_final_history = revoke
    results = engine.run_once()

    assert broker.orders == []
    assert results[0]["response"]["reason"] == "live_authorization_required"


@pytest.mark.parametrize("mode", ["live", "paper"])
def test_daily_history_recheck_blocks_when_market_closes_during_fetch(
    tmp_path: Path, mode: Literal["live", "paper"],
) -> None:
    broker = HistoryChangingBroker(())
    engine = make_engine(tmp_path, broker)
    engine.config = replace(engine.config, mode=mode)
    if mode == "paper":
        _write_paper_strategy(engine.strategy_artifact_paths, top_n=1, threshold=.99)

    def close_market() -> None:
        engine._clock = lambda: AUTO_TEST_NOW + timedelta(hours=6)

    broker.on_final_history = close_market
    results = engine.run_once()

    assert broker.orders == []
    assert results[0]["response"]["reason"] == "regular_market_closed"
    assert engine.trading_session_state.buy_count == 0


def test_daily_exception_stops_when_final_history_request_fails(tmp_path: Path) -> None:
    # Given: initial history is available, but the final broker query fails.
    broker = HistoryChangingBroker((), error=True)
    engine = make_engine(tmp_path, broker)
    # When
    results = engine.run_once()
    # Then: failure cannot consume the first-share exception or submit an order.
    assert broker.orders == []
    assert results[0]["response"]["reason"] == "daily_minimum_history_unavailable"
    _, claims = read_session_payload(engine.automatic_order_guard.session_store.path)
    assert [claim.status for claim in claims.values()] == [ClaimStatus.REJECTED]
    assert engine.trading_session_state.buy_count == 0


def test_daily_exception_submits_one_share_when_final_history_is_still_empty(tmp_path: Path) -> None:
    # Given: no completed or pending buy appears in either broker query.
    broker = HistoryChangingBroker(())
    engine = make_engine(tmp_path, broker)
    # When
    results = engine.run_once()
    # Then: the authorized one-share allowance remains usable.
    assert [(order.symbol, order.qty) for order in broker.orders] == [("WBD", 1)]
    assert results[0]["response"]["status"] == "accepted"
    assert broker.history_calls == 2
