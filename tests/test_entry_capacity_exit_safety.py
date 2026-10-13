from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import Position
from nasdaq_auto_trader.risk import RiskConfig
from tests.test_auto_symbol_engine import (
    AUTO_TEST_NOW,
    _AcceptedBroker,
    _guard,
    _write_paper_strategy,
)
from tests.test_automatic_entry_eligibility import price_bars
from tests.test_effective_entry_eligibility import CapacityMarketData


@dataclass(frozen=True, slots=True)
class FailedEntryCapacity(CapacityMarketData):
    failure: BrokerRequestError | OSError = field(default_factory=OSError)

    def get_overseas_buying_power(self, symbol: str, latest_price: float) -> float:
        if symbol == "AAPL":
            raise self.failure
        return 10000


@pytest.mark.parametrize("error_type", [BrokerRequestError, OSError])
@pytest.mark.parametrize("held", [True, False], ids=["timed_exit", "eligible_buy"])
def test_entry_capacity_failure_preserves_other_candidates_and_ordinary_exits(
    tmp_path: Path, error_type: type[BrokerRequestError] | type[OSError], held: bool,
) -> None:
    # Given: one candidate lookup fails while another symbol has a valid action.
    paths = StrategyArtifactPaths.from_root(tmp_path)
    _write_paper_strategy(paths, top_n=1)
    holdings = {"MSFT": Position("MSFT", 1, 4.19, 4.19)} if held else {}
    market = FailedEntryCapacity(
        {
            "AAPL": price_bars("AAPL", [100. + index for index in range(220)]),
            "MSFT": price_bars("MSFT", [2. + index * .01 for index in range(220)]),
        },
        holdings=holdings,
        failure=error_type("synthetic-sensitive-capacity-details"),
    )
    broker = _AcceptedBroker()
    engine = TradingEngine(
        AppConfig(broker="kis", risk=RiskConfig(order_qty=1, max_position_pct=.5)),
        broker=broker, market_data=market,
        trading_settings=TradingSettings(
            auto_symbol_selection_enabled=True,
            time_based_sell_enabled=True, max_holding_minutes=1,
        ),
        strategy_artifact_paths=paths, automatic_order_guard=_guard(paths, tmp_path),
        clock=lambda: AUTO_TEST_NOW,
    )
    if held:
        engine.trading_session_state.position_first_seen_at["MSFT"] = (
            AUTO_TEST_NOW - timedelta(minutes=10)
        )
    assert engine._protective_exit_symbols(market.bars, holdings) == []

    # When
    results = engine.run_once()

    # Then: the failed candidate stays excluded while the other action survives.
    assert [result["symbol"] for result in results] == ["MSFT"]
    assert results[0]["order"].side == ("sell" if held else "buy")
    assert results[0]["response"]["status"] == "dry_run"
    if held:
        assert "max_holding_minutes" in results[0]["decision"].reasons
    assert engine.last_selection_report is not None
    assert "entry_buying_power_unavailable:AAPL" in engine.last_selection_report.warnings
    assert not any(
        "synthetic-sensitive" in warning for warning in engine.last_selection_report.warnings
    )
    assert broker.orders == []
