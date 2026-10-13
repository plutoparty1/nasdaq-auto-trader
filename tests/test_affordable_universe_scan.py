from dataclasses import replace

from nasdaq_auto_trader.automatic_selection import (
    EntryEligibilityContext,
    prepare_automatic_selection,
)
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.quant_data.universe_snapshot import load_default_universe
from tests.test_automatic_entry_eligibility import (
    MarketData,
    price_bars,
    selection_request,
)

__all__ = ["selection_request"]


def test_affordable_candidate_is_considered_beyond_thirty_liquidity_leaders(selection_request):
    # Given: thirty expensive leaders displace the only affordable member.
    members = [item.symbol for item in load_default_universe().symbols]
    affordable = members[30]
    bars = {
        symbol: price_bars(symbol, [100. + index for index in range(220)])
        for symbol in members[:30]
    }
    bars[affordable] = price_bars(affordable, [2. + index * .01 for index in range(220)])
    request = replace(
        selection_request, market_data=MarketData(bars),
        entry_context=EntryEligibilityContext(AccountSnapshot(100, 100, 100), {}),
    )
    # When: account-aware selection evaluates the approved universe.
    result = prepare_automatic_selection(request)
    # Then: liquidity truncation cannot hide the executable one-share buy.
    assert result.report.selected_symbols == (affordable,)
    assert result.report.shortlist_count == 31


class RankedMarket(MarketData):
    def get_liquid_overseas_symbols(self, universe: set[str], limit: int = 30) -> tuple[str, ...]:
        return ("AAPL",)


def test_account_scan_includes_members_missing_from_broker_liquidity_ranking(selection_request):
    # Given: broker ranking has only an unaffordable member.
    bars = {
        "AAPL": price_bars("AAPL", [100. + index for index in range(220)]),
        "MSFT": price_bars("MSFT", [2. + index * .01 for index in range(220)]),
    }
    request = replace(
        selection_request,
        config=replace(selection_request.config, broker="kis"),
        market_data=RankedMarket(bars),
        entry_context=EntryEligibilityContext(AccountSnapshot(100, 100, 100), {}),
    )
    # When
    result = prepare_automatic_selection(request)
    # Then
    assert result.report.selected_symbols == ("MSFT",)
