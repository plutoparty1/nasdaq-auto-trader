from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.automatic_selection import (
    AutomaticSelectionRequest,
    EntryEligibilityContext,
    prepare_automatic_selection,
)
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.models import AccountSnapshot, Bar
from nasdaq_auto_trader.risk import RiskConfig
from tests.test_auto_symbol_engine import AUTO_TEST_NOW, _write_paper_strategy
from tests.test_automatic_entry_eligibility import price_bars


@dataclass(frozen=True, slots=True)
class IsolatedMarket:
    bars: dict[str, list[Bar]]
    bar_error: BrokerRequestError | OSError | None = None
    quote_error: BrokerRequestError | OSError | None = None
    failing_quote: JsonObject | None = field(
        default_factory=lambda: {"bp": 4.18, "ap": 4.19},
    )
    quoted_symbols: list[str] = field(default_factory=list)

    def get_stock_bars(
        self, symbols: list[str], timeframe: str, start: str,
        end: str | None = None, limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        if "AAPL" in symbols and self.bar_error is not None:
            raise self.bar_error
        return {symbol: self.bars[symbol] for symbol in symbols if symbol in self.bars}

    def get_latest_quotes(self, symbols: list[str]) -> dict[str, JsonObject]:
        self.quoted_symbols.extend(symbols)
        if "AAPL" in symbols and self.quote_error is not None:
            raise self.quote_error
        quotes: dict[str, JsonObject] = {}
        for symbol in symbols:
            if symbol == "AAPL":
                if self.failing_quote is not None:
                    quotes[symbol] = self.failing_quote
            else:
                quotes[symbol] = {"bp": 4.18, "ap": 4.19}
        return quotes


@dataclass(frozen=True, slots=True)
class BestQuoteMarket:
    source: IsolatedMarket

    def get_stock_bars(
        self, symbols: list[str], timeframe: str, start: str,
        end: str | None = None, limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        return self.source.get_stock_bars(symbols, timeframe, start, end, limit)

    def get_best_quote(self, symbol: str) -> JsonObject:
        return self.source.get_latest_quotes([symbol]).get(symbol, {})


@pytest.fixture
def entry_request(tmp_path: Path) -> AutomaticSelectionRequest:
    paths = StrategyArtifactPaths.from_root(tmp_path)
    _write_paper_strategy(paths, top_n=1)
    market = IsolatedMarket({
        symbol: price_bars(symbol, [2. + index * .01 for index in range(220)])
        for symbol in ("AAPL", "MSFT")
    })
    return AutomaticSelectionRequest(
        AppConfig(mode="paper", risk=RiskConfig(order_qty=1)),
        market, paths, AUTO_TEST_NOW,
        entry_context=EntryEligibilityContext(AccountSnapshot(100, 100, 100), {}),
    )


@pytest.mark.parametrize("error", [BrokerRequestError("private-details"), OSError("private-details")])
def test_account_scan_retains_good_candidate_when_member_bars_fail(
    entry_request: AutomaticSelectionRequest, error: BrokerRequestError | OSError,
) -> None:
    # Given: the leading member's data endpoint fails independently.
    assert isinstance(entry_request.market_data, IsolatedMarket)
    market = replace(entry_request.market_data, bar_error=error)
    # When: the account-aware scan loads every universe member.
    result = prepare_automatic_selection(replace(entry_request, market_data=market))
    # Then: the affordable member remains selectable, with sanitized diagnostics.
    assert result.report.selected_symbols == ("MSFT",)
    assert "entry_market_bars_unavailable:AAPL" in result.report.warnings
    assert "AAPL" not in market.quoted_symbols
    assert "private-details" not in repr(result.report)


@pytest.mark.parametrize("best_quote", [False, True])
@pytest.mark.parametrize("error", [BrokerRequestError("private-details"), OSError("private-details")])
def test_account_scan_retains_good_candidate_when_member_quote_fails(
    entry_request: AutomaticSelectionRequest,
    error: BrokerRequestError | OSError,
    best_quote: bool,
) -> None:
    # Given: only one member has an unavailable quote.
    assert isinstance(entry_request.market_data, IsolatedMarket)
    source = replace(entry_request.market_data, quote_error=error)
    market = BestQuoteMarket(source) if best_quote else source
    # When
    result = prepare_automatic_selection(replace(entry_request, market_data=market))
    # Then: a different member retains its actual quote and affordability checks.
    assert result.report.selected_symbols == ("MSFT",)
    assert result.quotes_by_symbol == {"MSFT": (4.18, 4.19)}
    assert "entry_market_quote_unavailable:AAPL" in result.report.warnings
    assert "private-details" not in repr(result.report)


@pytest.mark.parametrize("quote", [None, {}, {"bp": 0, "ap": 4.19}, {"bp": 5, "ap": 4}])
def test_account_scan_excludes_missing_or_invalid_quotes_without_synthesis(
    entry_request: AutomaticSelectionRequest, quote: JsonObject | None,
) -> None:
    # Given: one candidate has no trustworthy quote, while another has valid data.
    assert isinstance(entry_request.market_data, IsolatedMarket)
    market = replace(entry_request.market_data, failing_quote=quote)
    # When
    result = prepare_automatic_selection(replace(entry_request, market_data=market))
    # Then: invalid quotes cannot qualify for selection.
    assert result.report.selected_symbols == ("MSFT",)
    assert "AAPL" not in result.bars_by_symbol
    assert "AAPL" not in result.quotes_by_symbol
    assert "entry_market_quote_unavailable:AAPL" in result.report.warnings


def test_account_scan_skips_quote_requests_for_missing_bars(
    entry_request: AutomaticSelectionRequest,
) -> None:
    # Given: the snapshot still contains a member with no returned price history.
    assert isinstance(entry_request.market_data, IsolatedMarket)
    market = replace(entry_request.market_data, bars={"MSFT": entry_request.market_data.bars["MSFT"]})
    # When
    result = prepare_automatic_selection(replace(entry_request, market_data=market))
    # Then: only usable members require quotes and enter the learned ranking.
    assert result.report.selected_symbols == ("MSFT",)
    assert market.quoted_symbols == ["MSFT"]
    assert "entry_market_bars_missing:AAPL" in result.report.warnings


def test_legacy_scan_remains_blocked_by_a_member_quote_failure(
    entry_request: AutomaticSelectionRequest,
) -> None:
    # Given: the legacy scan has no account context.
    assert isinstance(entry_request.market_data, IsolatedMarket)
    market = replace(entry_request.market_data, quote_error=BrokerRequestError("quote_failed"))
    # When
    result = prepare_automatic_selection(replace(entry_request, market_data=market, entry_context=None))
    # Then: its all-or-nothing contract remains intact.
    assert result.report.status == "blocked"
    assert result.report.blocked_reasons == ("quote_failed",)
    assert result.report.selected_symbols == ()
