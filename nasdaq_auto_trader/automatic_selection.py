from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import math
from typing import Protocol, runtime_checkable

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject, JsonValue
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.models import Bar
from nasdaq_auto_trader.automatic_risk import (
    AutomaticRiskBlock,
    AutomaticRiskLimits,
    resolve_automatic_risk_limits,
)
from nasdaq_auto_trader.quant_data.features import PriceBar
from nasdaq_auto_trader.quant_data.market_quality import filter_tradeable_symbols
from nasdaq_auto_trader.quant_data.symbol_selector import (
    RankedSymbol,
    SelectionReport,
    StrategyResolutionBlock,
    blocked_selection_report,
    blocked_selection_report_without_snapshot,
    resolve_strategy,
    select_symbols_with_candidates,
)
from nasdaq_auto_trader.quant_data.universe_snapshot import (
    UniverseSnapshotError,
    load_default_universe,
    universe_freshness,
    UniverseSymbol,
)


class SelectionMarketData(Protocol):
    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]: ...


@runtime_checkable
class KISLiquidityMarketData(Protocol):
    def get_liquid_overseas_symbols(
        self,
        universe: set[str],
        limit: int = 30,
    ) -> tuple[str, ...]: ...


@runtime_checkable
class BatchQuoteMarketData(Protocol):
    def get_latest_quotes(self, symbols: list[str]) -> dict[str, JsonObject]: ...


@runtime_checkable
class BestQuoteMarketData(Protocol):
    def get_best_quote(self, symbol: str) -> JsonObject: ...


@dataclass(frozen=True, slots=True)
class AutomaticSelectionResult:
    report: SelectionReport
    bars_by_symbol: dict[str, list[Bar]]
    risk_limits: AutomaticRiskLimits | None = None
    quotes_by_symbol: dict[str, tuple[float, float]] = field(default_factory=dict)
    prethreshold_ranked: tuple[RankedSymbol, ...] = ()


@dataclass(frozen=True, slots=True)
class AutomaticSelectionRequest:
    config: AppConfig
    market_data: SelectionMarketData
    paths: StrategyArtifactPaths
    now: datetime
    daily_forced_order_enabled: bool = False


def prepare_automatic_selection(
    request: AutomaticSelectionRequest,
) -> AutomaticSelectionResult:
    config = request.config
    market_data = request.market_data
    paths = request.paths
    now = request.now
    try:
        snapshot = load_default_universe()
    except UniverseSnapshotError as exc:
        return AutomaticSelectionResult(
            blocked_selection_report_without_snapshot(exc.reason),
            {},
        )
    freshness = universe_freshness(snapshot, config.mode, now.date())
    if freshness.blocked_reason:
        report = blocked_selection_report(snapshot, freshness.blocked_reason)
        return AutomaticSelectionResult(report, {})
    resolution = resolve_strategy(config.mode, paths)
    if isinstance(resolution, StrategyResolutionBlock):
        report = blocked_selection_report(
            snapshot,
            resolution.reason,
            warnings=freshness.warnings,
        )
        return AutomaticSelectionResult(report, {})
    risk_limits = resolve_automatic_risk_limits(paths, resolution)
    if isinstance(risk_limits, AutomaticRiskBlock):
        report = blocked_selection_report(
            snapshot,
            risk_limits.reason,
            resolution,
            freshness.warnings,
        )
        return AutomaticSelectionResult(report, {})
    try:
        symbols = _shortlist_symbols(config, market_data, snapshot.symbols)
        legacy_bars = _load_bars(request, symbols)
        quotes = _load_quotes(request, symbols)
    except BrokerRequestError as exc:
        report = blocked_selection_report(
            snapshot,
            str(exc),
            resolution,
            freshness.warnings,
        )
        return AutomaticSelectionResult(report, {})
    price_bars = {
        symbol: [_price_bar(item) for item in bars]
        for symbol, bars in legacy_bars.items()
    }
    for symbol, (bid, ask) in quotes.items():
        bars = price_bars.get(symbol)
        if bars:
            bars[-1] = replace(bars[-1], bid=bid, ask=ask)
    quality = filter_tradeable_symbols(
        price_bars,
        now=now,
        quotes_required=config.mode != "dry_run",
    )
    ranked_quality = sorted(
        quality.symbols,
        key=lambda symbol: (
            -(price_bars[symbol][-1].close * price_bars[symbol][-1].volume),
            symbol,
        ),
    )[:30]
    selected_bars = {symbol: price_bars[symbol] for symbol in ranked_quality}
    report, candidates = select_symbols_with_candidates(
        snapshot,
        resolution,
        selected_bars,
        freshness.warnings,
    )
    return AutomaticSelectionResult(
        report,
        {symbol: legacy_bars[symbol] for symbol in ranked_quality},
        risk_limits,
        {symbol: quotes[symbol] for symbol in ranked_quality if symbol in quotes},
        candidates,
    )


def _shortlist_symbols(
    config: AppConfig,
    market_data: SelectionMarketData,
    universe_symbols: tuple[UniverseSymbol, ...],
) -> list[str]:
    members = {item.symbol for item in universe_symbols}
    if config.broker == "kis" and isinstance(market_data, KISLiquidityMarketData):
        return list(market_data.get_liquid_overseas_symbols(members, 30))
    return sorted(members)


def _load_bars(
    request: AutomaticSelectionRequest,
    symbols: list[str],
) -> dict[str, list[Bar]]:
    config = request.config
    now = request.now
    start = now - timedelta(days=config.lookback_days)
    return dict(
        request.market_data.get_stock_bars(
            symbols,
            config.timeframe,
            start.date().isoformat(),
            now.date().isoformat(),
            config.bar_limit,
        )
    )


def _load_quotes(
    request: AutomaticSelectionRequest,
    symbols: list[str],
) -> dict[str, tuple[float, float]]:
    config = request.config
    market_data = request.market_data
    if config.mode == "dry_run":
        return {}
    if isinstance(market_data, BatchQuoteMarketData):
        return _parsed_quotes(symbols, market_data.get_latest_quotes(symbols))
    if isinstance(market_data, BestQuoteMarketData):
        return _parsed_quotes(
            symbols,
            {symbol: market_data.get_best_quote(symbol) for symbol in symbols},
        )
    raise BrokerRequestError("market_quote_provider_unavailable")


def _parsed_quotes(
    symbols: list[str],
    payloads: dict[str, JsonObject],
) -> dict[str, tuple[float, float]]:
    if set(payloads) != set(symbols):
        raise BrokerRequestError("market_quote_batch_incomplete")
    return {
        symbol: _quote_prices(payloads[symbol])
        for symbol in symbols
    }


def _quote_prices(payload: JsonObject) -> tuple[float, float]:
    bid = _first_number(payload, ("bp", "pbid1", "bid"))
    ask = _first_number(payload, ("ap", "pask1", "ask"))
    if bid <= 0 or ask < bid:
        raise BrokerRequestError("market_quote_invalid")
    return bid, ask


def _first_number(payload: JsonObject, keys: tuple[str, ...]) -> float:
    for key in keys:
        value: JsonValue | None = payload.get(key)
        if value in (None, ""):
            continue
        try:
            number = float(str(value).replace(",", ""))
        except ValueError:
            continue
        if math.isfinite(number):
            return number
    return 0.0


def _price_bar(bar: Bar) -> PriceBar:
    return PriceBar(
        symbol=bar.symbol,
        timestamp=bar.timestamp,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
    )
