from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from nasdaq_auto_trader.live_canary_selection import (
    MAX_DAILY_GETS,
    CanaryScanRequest,
    DailyGetBudget,
    scan_canary_candidates,
)


class FakeMarket:
    def __init__(self, ranked: tuple[str, ...]) -> None:
        self.ranked = ranked
        self.details: dict[str, Mapping[str, str]] = {}
        self.quotes: dict[str, Mapping[str, str]] = {}
        self.calls: list[tuple[str, str]] = []

    def get_trade_volume_universe(self, universe: set[str]) -> tuple[str, ...]:
        self.calls.append(("rank", str(len(universe))))
        return tuple(symbol for symbol in self.ranked if symbol in universe)

    def get_price_detail(self, symbol: str) -> Mapping[str, str]:
        self.calls.append(("detail", symbol))
        return self.details[symbol]

    def get_best_quote(self, symbol: str) -> Mapping[str, str]:
        self.calls.append(("quote", symbol))
        return self.quotes[symbol]


class AdvancingClock:
    def __init__(self, step: float = 0.0) -> None:
        self.value = 0.0
        self.step = step

    def __call__(self) -> float:
        current = self.value
        self.value += self.step
        return current


def _market(*symbols: str) -> FakeMarket:
    market = FakeMarket(tuple(symbols))
    for symbol in symbols:
        market.details[symbol] = {"last": "19.50", "tvol": "500000"}
        market.quotes[symbol] = {
            "pbid1": "19.40",
            "pask1": "19.50",
            "vbid1": "300",
            "vask1": "300",
        }
    return market


def test_scan_selects_ranked_candidate_after_liquidity_and_spread_filters() -> None:
    market = _market("WIDE", "SAFE")
    market.quotes["WIDE"] = {
        "pbid1": "18.00",
        "pask1": "19.50",
        "vbid1": "300",
        "vask1": "300",
    }
    request = CanaryScanRequest(
        frozenset({"WIDE", "SAFE"}), Decimal("20.00"), DailyGetBudget()
    )

    result = scan_canary_candidates(request, market)

    assert result.candidate is not None
    assert result.candidate.symbol == "SAFE"
    assert result.candidate.quantity == 1
    assert result.inspected_symbols == ("WIDE", "SAFE")
    assert [kind for kind, _ in market.calls] == [
        "rank",
        "detail",
        "quote",
        "detail",
        "quote",
    ]


def test_scan_never_deep_inspects_more_than_ten_ranked_symbols() -> None:
    symbols = tuple(f"S{i:02d}" for i in range(30))
    market = _market(*symbols)
    for symbol in symbols:
        market.quotes[symbol] = {
            "pbid1": "10.00",
            "pask1": "19.50",
            "vbid1": "300",
            "vask1": "300",
        }
    request = CanaryScanRequest(
        frozenset(symbols), Decimal("20.00"), DailyGetBudget()
    )

    result = scan_canary_candidates(request, market)

    assert result.candidate is None
    assert len(result.inspected_symbols) == 10
    assert result.get_calls == 21
    assert market.calls.count(("rank", "30")) == 1


def test_scan_fails_closed_at_daily_get_budget_and_wall_budget() -> None:
    exhausted_budget = DailyGetBudget(used=MAX_DAILY_GETS)
    exhausted_market = _market("SAFE")
    exhausted = CanaryScanRequest(
        frozenset({"SAFE"}), Decimal("20.00"), exhausted_budget
    )
    wall_market = _market("SAFE")
    wall_request = CanaryScanRequest(
        frozenset({"SAFE"}), Decimal("20.00"), DailyGetBudget()
    )

    no_gets = scan_canary_candidates(exhausted, exhausted_market)
    over_wall = scan_canary_candidates(
        wall_request, wall_market, AdvancingClock(121.0)
    )

    assert no_gets.candidate is None
    assert no_gets.reason == "daily_get_budget_exhausted"
    assert exhausted_market.calls == []
    assert over_wall.candidate is None
    assert over_wall.reason == "scan_wall_budget_exhausted"
    assert [kind for kind, _ in wall_market.calls] == ["rank"]


def test_scan_requires_exact_cash_boundary_and_rejects_price_above_entry_cap() -> None:
    market = _market("BOUNDARY", "TOO_HIGH")
    market.details["TOO_HIGH"] = {"last": "19.50", "tvol": "500000"}
    market.quotes["TOO_HIGH"] = {
        "pbid1": "19.40",
        "pask1": "19.51",
        "vbid1": "300",
        "vask1": "300",
    }
    exact = CanaryScanRequest(
        frozenset({"BOUNDARY", "TOO_HIGH"}), Decimal("20.00"), DailyGetBudget()
    )
    short = CanaryScanRequest(
        frozenset({"BOUNDARY"}), Decimal("19.99"), DailyGetBudget()
    )

    accepted = scan_canary_candidates(exact, market)
    rejected = scan_canary_candidates(short, _market("BOUNDARY"))

    assert accepted.candidate is not None
    assert accepted.candidate.entry_price == Decimal("19.50")
    assert rejected.candidate is None


def test_scan_does_not_return_entry_when_final_scan_get_reaches_daily_cap() -> None:
    market = _market("SAFE")
    budget = DailyGetBudget(used=MAX_DAILY_GETS - 3)
    request = CanaryScanRequest(frozenset({"SAFE"}), Decimal("20.00"), budget)

    result = scan_canary_candidates(request, market)

    assert result.candidate is None
    assert result.reason == "daily_get_budget_exhausted"
    assert budget.used == MAX_DAILY_GETS
