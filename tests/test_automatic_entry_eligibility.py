from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import nasdaq_auto_trader.automatic_selection as selection
from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.automatic_selection_production import (
    prepare_production_automatic_selection,
)
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.strategy import TechnicalStrategy
from tests.test_auto_symbol_engine import (
    AUTO_TEST_NOW,
    _AcceptedBroker,
    _guard,
    _write_paper_strategy,
)


@dataclass(frozen=True, slots=True)
class MarketData:
    bars: dict[str, list[Bar]]

    def get_stock_bars(
        self, symbols: list[str], timeframe: str, start: str,
        end: str | None = None, limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        return {symbol: bars for symbol, bars in self.bars.items() if symbol in symbols}

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        return AccountSnapshot(10000, 10000, 10000)

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        return {}


def price_bars(symbol: str, closes: list[float]) -> list[Bar]:
    return [
        Bar(symbol, "2026-07-10T16:00:00+00:00", close, close * 1.001,
            close * .999, close, 1_000_000)
        for close in closes
    ]


@pytest.fixture
def selection_request(tmp_path: Path) -> selection.AutomaticSelectionRequest:
    paths = StrategyArtifactPaths.from_root(tmp_path)
    _write_paper_strategy(paths, top_n=1)
    return selection.AutomaticSelectionRequest(
        AppConfig(risk=RiskConfig(order_qty=1)),
        MarketData({}), paths, AUTO_TEST_NOW,
    )


def test_selects_lower_ranked_buy_when_leader_is_technical_hold(selection_request):
    # Given: the strongest recent rebound remains below its long regime.
    bars = {
        "AAPL": price_bars("AAPL", [200.] * 180 + [50. + i for i in range(40)]),
        "MSFT": price_bars("MSFT", [100. + i * .2 for i in range(220)]),
    }
    selection_request = replace(selection_request, market_data=MarketData(bars))
    baseline = selection.prepare_automatic_selection(selection_request)
    assert baseline.report.selected_symbols == ("AAPL",)
    assert TechnicalStrategy().decide("AAPL", bars["AAPL"], None).action == "hold"
    assert TechnicalStrategy().decide("MSFT", bars["MSFT"], None).action == "buy"
    context = selection.EntryEligibilityContext(AccountSnapshot(10000, 10000, 10000), {})
    # When: eligibility is applied before the learned top-one selection.
    result = selection.prepare_automatic_selection(replace(selection_request, entry_context=context))
    # Then: an actual buy is selected, without changing learned scores.
    assert result.report.selected_symbols == ("MSFT",)
    assert "entry_technical_hold:AAPL:below_long_regime" in result.report.warnings
    _write_paper_strategy(selection_request.paths, top_n=2)
    unfiltered = selection.prepare_automatic_selection(selection_request)
    assert result.report.ranked == tuple(
        item for item in unfiltered.report.ranked if item.symbol == "MSFT"
    )


def test_selects_affordable_candidate_when_top_buy_exceeds_position_cap(selection_request):
    # Given: both buy, but only the lower learned rank fits the unchanged cap.
    bars = {
        "AAPL": price_bars("AAPL", [100. + i for i in range(220)]),
        "MSFT": price_bars("MSFT", [2. + i * .01 for i in range(220)]),
    }
    selection_request = replace(selection_request, market_data=MarketData(bars))
    assert selection.prepare_automatic_selection(selection_request).report.selected_symbols == ("AAPL",)
    context = selection.EntryEligibilityContext(AccountSnapshot(100, 100, 100), {})
    # When
    result = selection.prepare_automatic_selection(replace(selection_request, entry_context=context))
    # Then
    assert result.report.selected_symbols == ("MSFT",)
    assert "entry_risk_capacity:AAPL" in result.report.warnings


def test_no_eligible_entry_reports_no_trade_and_retains_held_exit_bars(selection_request):
    # Given: a held symbol and an unaffordable new buy.
    bars = {
        "AAPL": price_bars("AAPL", [100. + i for i in range(220)]),
        "MSFT": price_bars("MSFT", [100. + i * .2 for i in range(220)]),
    }
    context = selection.EntryEligibilityContext(
        AccountSnapshot(63, 63, 63), {"MSFT": Position("MSFT", 1, 140, 200)},
    )
    # When
    result = selection.prepare_automatic_selection(
        replace(selection_request, market_data=MarketData(bars), entry_context=context),
    )
    # Then
    assert result.report.status == "no_trade"
    assert result.report.blocked_reasons == ("entry_eligibility_no_candidates",)
    assert result.report.selected_symbols == ()
    assert result.bars_by_symbol["MSFT"] == bars["MSFT"]


def test_account_aware_selection_bypasses_account_unaware_cache(selection_request, monkeypatch, tmp_path):
    # Given: an existing cached top-one result for an unaffordable symbol.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    bars = {
        "AAPL": price_bars("AAPL", [100. + i for i in range(220)]),
        "MSFT": price_bars("MSFT", [2. + i * .01 for i in range(220)]),
    }
    selection_request = replace(selection_request, market_data=MarketData(bars))
    assert prepare_production_automatic_selection(selection_request).report.selected_symbols == ("AAPL",)
    context = selection.EntryEligibilityContext(AccountSnapshot(100, 100, 100), {})
    # When
    result = prepare_production_automatic_selection(replace(selection_request, entry_context=context))
    # Then
    assert result.report.selected_symbols == ("MSFT",)


def test_eligible_candidate_below_learned_threshold_is_not_forced(selection_request):
    bars = {
        "AAPL": price_bars("AAPL", [100. + i for i in range(220)]),
        "MSFT": price_bars("MSFT", [2. + i * .01 for i in range(220)]),
    }
    _write_paper_strategy(selection_request.paths, top_n=1, threshold=.99)
    context = selection.EntryEligibilityContext(AccountSnapshot(100, 100, 100), {})

    result = selection.prepare_automatic_selection(
        replace(selection_request, market_data=MarketData(bars), entry_context=context),
    )

    assert result.report.status == "no_trade"
    assert result.report.selected_symbols == ()


def test_engine_builds_dry_run_buy_for_lower_ranked_eligible_symbol(selection_request, tmp_path):
    bars = {
        "AAPL": price_bars("AAPL", [200.] * 180 + [50. + i for i in range(40)]),
        "MSFT": price_bars("MSFT", [100. + i * .2 for i in range(220)]),
    }
    broker = _AcceptedBroker()
    engine = TradingEngine(
        selection_request.config, broker=broker, market_data=MarketData(bars),
        trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
        strategy_artifact_paths=selection_request.paths,
        automatic_order_guard=_guard(selection_request.paths, tmp_path),
        clock=lambda: AUTO_TEST_NOW,
    )

    results = engine.run_once()

    assert len(results) == 1
    assert results[0]["symbol"] == "MSFT"
    assert results[0]["decision"].action == "buy"
    assert results[0]["order"].side == "buy"
    assert broker.orders == []
