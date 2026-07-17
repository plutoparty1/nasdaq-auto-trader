from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Final, Protocol, TypeAlias

from .live_canary_policy import CANARY_POLICY


MAX_DAILY_GETS: Final = CANARY_POLICY.daily_get_budget
MAX_SPREAD_PCT: Final = 0.75
MIN_QUOTE_DEPTH: Final = 500.0
MIN_VOLUME: Final = 500_000.0
MIN_DOLLAR_VOLUME: Final = 5_000_000.0

MarketField: TypeAlias = str | int | float | None


class ReadOnlyCanaryMarket(Protocol):
    def get_trade_volume_universe(self, universe: set[str]) -> tuple[str, ...]: ...

    def get_price_detail(self, symbol: str) -> Mapping[str, MarketField]: ...

    def get_best_quote(self, symbol: str) -> Mapping[str, MarketField]: ...


@dataclass(frozen=True, slots=True)
class CanaryBudgetError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


class DailyGetBudget:
    __slots__ = ("used",)

    def __init__(self, used: int = 0) -> None:
        if isinstance(used, bool) or used < 0 or used > MAX_DAILY_GETS:
            raise CanaryBudgetError("daily GET usage is outside the fixed budget")
        self.used = used

    @property
    def remaining(self) -> int:
        return MAX_DAILY_GETS - self.used

    def consume(self) -> bool:
        if self.used >= MAX_DAILY_GETS:
            return False
        self.used += 1
        return True


@dataclass(frozen=True, slots=True)
class CanaryScanRequest:
    universe: frozenset[str]
    cash_available_usd: Decimal
    budget: DailyGetBudget


@dataclass(frozen=True, slots=True)
class CanaryCandidate:
    symbol: str
    rank: int
    quantity: int
    entry_price: Decimal
    bid: float
    ask: float
    spread_pct: float
    quote_depth: float
    volume: float
    dollar_volume: float


@dataclass(frozen=True, slots=True)
class CanaryScanResult:
    candidate: CanaryCandidate | None
    ranked_symbols: tuple[str, ...]
    inspected_symbols: tuple[str, ...]
    get_calls: int
    reason: str


def scan_canary_candidates(
    request: CanaryScanRequest,
    market: ReadOnlyCanaryMarket,
    clock: Callable[[], float] = time.monotonic,
) -> CanaryScanResult:
    started_at = clock()
    initial_gets = request.budget.used
    if not request.budget.consume():
        return _result((), (), request.budget.used - initial_gets, "daily_get_budget_exhausted")
    try:
        ranked = market.get_trade_volume_universe(set(request.universe))
    except (LookupError, OSError, RuntimeError, TimeoutError, TypeError, ValueError):
        return _result((), (), request.budget.used - initial_gets, "rank_get_failed")
    if not _within_wall_budget(started_at, clock):
        symbols = tuple(ranked[: CANARY_POLICY.rank_top_symbols])
        return _result(symbols, (), request.budget.used - initial_gets, "scan_wall_budget_exhausted")

    ranked_symbols = tuple(
        symbol
        for symbol in ranked[: CANARY_POLICY.rank_top_symbols]
        if symbol in request.universe
    )
    inspected: list[str] = []
    for rank, symbol in enumerate(ranked_symbols, start=1):
        if len(inspected) >= CANARY_POLICY.deep_inspect_symbols:
            break
        if not _within_wall_budget(started_at, clock):
            return _result(ranked_symbols, tuple(inspected), request.budget.used - initial_gets, "scan_wall_budget_exhausted")
        if not request.budget.consume():
            return _result(ranked_symbols, tuple(inspected), request.budget.used - initial_gets, "daily_get_budget_exhausted")
        inspected.append(symbol)
        try:
            detail = market.get_price_detail(symbol)
        except (LookupError, OSError, RuntimeError, TimeoutError, TypeError, ValueError):
            return _result(ranked_symbols, tuple(inspected), request.budget.used - initial_gets, "detail_get_failed")
        if not _within_wall_budget(started_at, clock):
            return _result(ranked_symbols, tuple(inspected), request.budget.used - initial_gets, "scan_wall_budget_exhausted")
        if not request.budget.consume():
            return _result(ranked_symbols, tuple(inspected), request.budget.used - initial_gets, "daily_get_budget_exhausted")
        try:
            quote = market.get_best_quote(symbol)
        except (LookupError, OSError, RuntimeError, TimeoutError, TypeError, ValueError):
            return _result(ranked_symbols, tuple(inspected), request.budget.used - initial_gets, "quote_get_failed")
        if not _within_wall_budget(started_at, clock):
            return _result(ranked_symbols, tuple(inspected), request.budget.used - initial_gets, "scan_wall_budget_exhausted")
        candidate = _candidate(rank, symbol, detail, quote, request.cash_available_usd)
        if candidate is not None:
            if request.budget.used >= MAX_DAILY_GETS:
                return _result(
                    ranked_symbols,
                    tuple(inspected),
                    request.budget.used - initial_gets,
                    "daily_get_budget_exhausted",
                )
            return _result(ranked_symbols, tuple(inspected), request.budget.used - initial_gets, "selected", candidate)
    reason = "daily_get_budget_exhausted" if request.budget.used >= MAX_DAILY_GETS else "no_eligible_candidate"
    return _result(ranked_symbols, tuple(inspected), request.budget.used - initial_gets, reason)


def _candidate(
    rank: int,
    symbol: str,
    detail: Mapping[str, MarketField],
    quote: Mapping[str, MarketField],
    cash_available_usd: Decimal,
) -> CanaryCandidate | None:
    last = _number(detail, "last", "ovrs_nmix_prpr", "stck_prpr")
    bid = _number(quote, "pbid1", "bid")
    ask = _number(quote, "pask1", "ask")
    entry_price = ask if ask > 0 else last
    volume = _number(detail, "tvol", "acml_vol", "volume")
    bid_size = _number(quote, "vbid1", "dbid1")
    ask_size = _number(quote, "vask1", "dask1")
    midpoint = (bid + ask) / 2
    spread_pct = (ask - bid) / midpoint * 100 if midpoint > 0 else 0.0
    quote_depth = bid_size + ask_size
    dollar_volume = volume * last
    required_cash = (
        _decimal(entry_price) + CANARY_POLICY.reserved_fee_buffer_usd
        if entry_price > 0
        else Decimal("0")
    )
    if (
        last <= 0
        or entry_price <= 0
        or entry_price > float(CANARY_POLICY.entry_limit_price_usd)
        or bid <= 0
        or ask <= 0
        or ask < bid
        or spread_pct <= 0
        or spread_pct > MAX_SPREAD_PCT
        or quote_depth < MIN_QUOTE_DEPTH
        or volume < MIN_VOLUME
        or dollar_volume < MIN_DOLLAR_VOLUME
        or required_cash > CANARY_POLICY.total_cash_gate_usd
        or cash_available_usd < required_cash
    ):
        return None
    return CanaryCandidate(
        symbol=symbol,
        rank=rank,
        quantity=CANARY_POLICY.quantity,
        entry_price=_decimal(entry_price),
        bid=bid,
        ask=ask,
        spread_pct=spread_pct,
        quote_depth=quote_depth,
        volume=volume,
        dollar_volume=dollar_volume,
    )


def _number(payload: Mapping[str, MarketField], *keys: str) -> float:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "" or isinstance(value, bool):
            continue
        try:
            number = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if isfinite(number):
            return number
    return 0.0


def _decimal(value: float) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _within_wall_budget(started_at: float, clock: Callable[[], float]) -> bool:
    return clock() - started_at < CANARY_POLICY.scan_wall_budget_seconds


def _result(
    ranked: tuple[str, ...],
    inspected: tuple[str, ...],
    get_calls: int,
    reason: str,
    candidate: CanaryCandidate | None = None,
) -> CanaryScanResult:
    return CanaryScanResult(candidate, ranked, inspected, get_calls, reason)
