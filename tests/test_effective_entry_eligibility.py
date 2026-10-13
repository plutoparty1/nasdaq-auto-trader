import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, assert_never

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.automatic_selection import (
    AutomaticSelectionRequest,
    prepare_automatic_selection,
)
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
from tests.test_automatic_entry_eligibility import MarketData, price_bars


@dataclass(frozen=True, slots=True)
class CapacityMarketData(MarketData):
    capacity: dict[str, float] = field(default_factory=dict)
    holdings: dict[str, Position] = field(default_factory=dict)

    def get_overseas_buying_power(self, symbol: str, latest_price: float) -> float:
        return self.capacity.get(symbol, 10000)

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        return self.holdings


@pytest.mark.parametrize("constraint", ["learned_notional", "kis_capacity", "settings"])
def test_engine_selects_feasible_lower_rank_when_leader_fails_effective_guard(
    tmp_path: Path, constraint: Literal["learned_notional", "kis_capacity", "settings"],
) -> None:
    # Given: the learned top-one leader is infeasible under one final order guard.
    paths = StrategyArtifactPaths.from_root(tmp_path)
    _write_paper_strategy(paths, top_n=1)
    market = CapacityMarketData({
        "AAPL": price_bars("AAPL", [100. + index for index in range(220)]),
        "MSFT": price_bars("MSFT", [2. + index * .01 for index in range(220)]),
    })
    config = AppConfig(risk=RiskConfig(order_qty=1, max_position_pct=.5))
    settings = TradingSettings(auto_symbol_selection_enabled=True)
    expected_warning = "entry_learned_risk:AAPL:learned_max_order_notional_reached"
    match constraint:
        case "learned_notional":
            assert paths.ai_config_path is not None
            paths.ai_config_path.write_text(json.dumps({"max_order_notional": 100}))
        case "kis_capacity":
            config = replace(config, broker="kis")
            market = replace(market, capacity={"AAPL": 0, "MSFT": 10000})
            expected_warning = "entry_risk_capacity:AAPL"
        case "settings":
            config = replace(config, broker="kis")
            market = replace(market, capacity={"AAPL": 1000, "MSFT": 10000})
            settings = replace(settings, min_cash_to_buy=2000)
            expected_warning = "entry_settings:AAPL:min_cash_to_buy_not_met"
        case unreachable:
            assert_never(unreachable)
    baseline = prepare_automatic_selection(
        AutomaticSelectionRequest(config, market, paths, AUTO_TEST_NOW),
    )
    assert baseline.report.selected_symbols == ("AAPL",)
    broker = _AcceptedBroker()
    engine = TradingEngine(
        config, broker=broker, market_data=market, trading_settings=settings,
        strategy_artifact_paths=paths, automatic_order_guard=_guard(paths, tmp_path),
        clock=lambda: AUTO_TEST_NOW,
    )

    # When: the real automatic engine runs with the same top-one strategy.
    results = engine.run_once()

    # Then: the feasible lower rank receives the existing guarded dry-run buy.
    assert [item["symbol"] for item in results] == ["MSFT"]
    assert results[0]["order"].side == "buy"
    assert results[0]["response"]["status"] == "dry_run"
    assert engine.last_selection_report is not None
    assert engine.last_selection_report.selected_symbols == ("MSFT",)
    assert expected_warning in engine.last_selection_report.warnings
    assert broker.orders == []


def test_engine_keeps_candidate_when_learned_limit_can_resize_notional(
    tmp_path: Path,
) -> None:
    # Given: a fractional order may be resized by the existing learned risk guard.
    paths = StrategyArtifactPaths.from_root(tmp_path)
    _write_paper_strategy(paths, top_n=1)
    assert paths.ai_config_path is not None
    paths.ai_config_path.write_text(json.dumps({"max_order_notional": 100}))
    market = MarketData({
        "AAPL": price_bars("AAPL", [100. + index for index in range(220)]),
    })
    broker = _AcceptedBroker()
    engine = TradingEngine(
        AppConfig(risk=RiskConfig(max_position_pct=.5)),
        broker=broker, market_data=market,
        trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
        strategy_artifact_paths=paths, automatic_order_guard=_guard(paths, tmp_path),
        clock=lambda: AUTO_TEST_NOW,
    )

    # When
    results = engine.run_once()

    # Then: screening preserves the guard's existing notional resizing behavior.
    assert len(results) == 1
    assert results[0]["symbol"] == "AAPL"
    assert results[0]["order"].notional == 100
    assert results[0]["response"]["status"] == "dry_run"
    assert broker.orders == []


def test_engine_reports_no_trade_when_all_candidates_fail_symbol_capacity(
    tmp_path: Path,
) -> None:
    # Given: all signals pass, but the broker has no symbol-specific buying power.
    paths = StrategyArtifactPaths.from_root(tmp_path)
    _write_paper_strategy(paths, top_n=1)
    market = CapacityMarketData(
        {"AAPL": price_bars("AAPL", [100. + index for index in range(220)])},
        capacity={"AAPL": 0},
    )
    broker = _AcceptedBroker()
    engine = TradingEngine(
        AppConfig(broker="kis", risk=RiskConfig(order_qty=1, max_position_pct=.5)),
        broker=broker, market_data=market,
        trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
        strategy_artifact_paths=paths, automatic_order_guard=_guard(paths, tmp_path),
        clock=lambda: AUTO_TEST_NOW,
    )

    # When
    results = engine.run_once()

    # Then: no alternate or forced order bypasses the failed capacity check.
    assert results == []
    assert engine.last_selection_report is not None
    assert engine.last_selection_report.status == "no_trade"
    assert engine.last_selection_report.selected_symbols == ()
    assert broker.orders == []


class EntryCapacityUnavailable(CapacityMarketData):
    def get_overseas_buying_power(self, symbol: str, latest_price: float) -> float:
        if symbol == "AAPL":
            raise BrokerRequestError("entry_capacity_unavailable")
        return 10000


def test_engine_retains_protective_exit_when_entry_capacity_is_unavailable(
    tmp_path: Path,
) -> None:
    # Given: a held stop-loss exit takes priority over a new entry lookup failure.
    paths = StrategyArtifactPaths.from_root(tmp_path)
    _write_paper_strategy(paths, top_n=1)
    market = EntryCapacityUnavailable(
        {
            "AAPL": price_bars("AAPL", [100. + index for index in range(220)]),
            "MSFT": price_bars("MSFT", [2. + index * .01 for index in range(220)]),
        },
        holdings={"MSFT": Position("MSFT", 1, 4.19, 10)},
    )
    broker = _AcceptedBroker()
    engine = TradingEngine(
        AppConfig(broker="kis", risk=RiskConfig(order_qty=1, max_position_pct=.5)),
        broker=broker, market_data=market,
        trading_settings=TradingSettings(auto_symbol_selection_enabled=True, sell_only=True),
        strategy_artifact_paths=paths, automatic_order_guard=_guard(paths, tmp_path),
        clock=lambda: AUTO_TEST_NOW,
    )

    # When
    results = engine.run_once()

    # Then: the existing stop loss remains executable without screening new buys.
    assert len(results) == 1
    assert results[0]["symbol"] == "MSFT"
    assert results[0]["order"].side == "sell"
    assert "fixed_stop_loss" in results[0]["decision"].reasons
    assert results[0]["response"]["status"] == "dry_run"
    assert broker.orders == []
