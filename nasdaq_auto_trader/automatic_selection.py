from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.automatic_entry_eligibility import EntryEligibilityContext
from nasdaq_auto_trader.automatic_risk import (
    AutomaticRiskBlock,
    AutomaticRiskLimits,
    resolve_automatic_risk_limits,
)
from nasdaq_auto_trader.automatic_selection_data import (
    BatchQuoteMarketData,
    BestQuoteMarketData,
    KISLiquidityMarketData,
    SelectionMarketData,
    _first_number,
    _load_bars,
    _load_quotes,
    _parsed_quotes,
    _price_bar,
    _quote_prices,
    load_entry_market_data,
)
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.models import Bar
from nasdaq_auto_trader.quant_data.market_quality import filter_tradeable_symbols
from nasdaq_auto_trader.quant_data.symbol_selector import (
    SelectionReport,
    StrategyResolutionBlock,
    blocked_selection_report,
    blocked_selection_report_without_snapshot,
    resolve_strategy,
    select_symbols,
)
from nasdaq_auto_trader.quant_data.universe_snapshot import (
    UniverseSnapshotError,
    UniverseSymbol,
    load_default_universe,
    universe_freshness,
)

__all__ = [
    "AutomaticSelectionRequest",
    "AutomaticSelectionResult",
    "BatchQuoteMarketData",
    "BestQuoteMarketData",
    "EntryEligibilityContext",
    "KISLiquidityMarketData",
    "SelectionMarketData",
    "_first_number",
    "_load_bars",
    "_load_quotes",
    "_parsed_quotes",
    "_price_bar",
    "_quote_prices",
    "prepare_automatic_selection",
]


@dataclass(frozen=True, slots=True)
class AutomaticSelectionResult:
    report: SelectionReport
    bars_by_symbol: dict[str, list[Bar]]
    risk_limits: AutomaticRiskLimits | None = None
    quotes_by_symbol: dict[str, tuple[float, float]] = field(default_factory=dict)
    daily_loss_breached: bool = False


@dataclass(frozen=True, slots=True)
class AutomaticSelectionRequest:
    config: AppConfig
    market_data: SelectionMarketData
    paths: StrategyArtifactPaths
    now: datetime
    entry_context: EntryEligibilityContext | None = None


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
    risk_limits = resolve_automatic_risk_limits(paths, resolution, candidate_risk=config.risk)
    if isinstance(risk_limits, AutomaticRiskBlock):
        report = blocked_selection_report(
            snapshot,
            risk_limits.reason,
            resolution,
            freshness.warnings,
        )
        return AutomaticSelectionResult(report, {})
    daily_minimum_due = bool(
        request.entry_context is not None and request.entry_context.daily_minimum_due
    )
    data_warnings: tuple[str, ...] = ()
    try:
        symbols = (
            sorted(item.symbol for item in snapshot.symbols)
            if request.entry_context is not None
            else _shortlist_symbols(config, market_data, snapshot.symbols)
        )
        if request.entry_context is None:
            legacy_bars = _load_bars(request, symbols)
            quotes = _load_quotes(request, symbols)
        else:
            entry_data = load_entry_market_data(request, symbols)
            legacy_bars = entry_data.bars_by_symbol
            quotes = entry_data.quotes_by_symbol
            data_warnings = entry_data.warnings
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
    )
    if request.entry_context is None:
        ranked_quality = ranked_quality[:30]
    selected_bars = {symbol: price_bars[symbol] for symbol in ranked_quality}
    eligible_symbols = None
    daily_loss_breached = False
    warnings = (*freshness.warnings, *data_warnings)
    if request.entry_context is not None:
        context = replace(
            request.entry_context,
            entry_prices={symbol: quote[1] for symbol, quote in quotes.items()},
        )
        eligibility = context.evaluate(
            config, {symbol: legacy_bars[symbol] for symbol in ranked_quality},
            risk_limits, now,
        )
        eligible_symbols = eligibility.eligible_symbols
        daily_loss_breached = eligibility.daily_loss_breached
        warnings = (*warnings, *eligibility.warnings)
    report = select_symbols(
        snapshot,
        resolution,
        selected_bars,
        warnings,
        eligible_symbols=eligible_symbols,
        daily_minimum_due=daily_minimum_due,
    )
    return AutomaticSelectionResult(
        report,
        {symbol: legacy_bars[symbol] for symbol in ranked_quality},
        risk_limits,
        {symbol: quotes[symbol] for symbol in ranked_quality if symbol in quotes},
        daily_loss_breached,
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
