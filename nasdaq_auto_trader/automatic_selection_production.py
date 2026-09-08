from __future__ import annotations

import hashlib
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from .ai_quant_lab.audit_logger import AuditEvent, AuditLogger
from .automatic_selection import (
    AutomaticSelectionResult,
    AutomaticSelectionRequest,
    _load_bars,
    _load_quotes,
    _price_bar,
    prepare_automatic_selection,
)
from .automatic_risk import AutomaticRiskBlock, resolve_automatic_risk_limits
from .brokers.common import BrokerRequestError
from .quant_data.market_quality import filter_tradeable_symbols
from .quant_data.resources import application_data_root
from .quant_data.selection_cache import SelectionCache, SelectionCacheIdentity
from .quant_data.symbol_selector import (
    ResolvedStrategy,
    SelectionReport,
    StrategyResolutionBlock,
    resolve_strategy,
    blocked_selection_report_without_snapshot,
)
from .quant_data.universe_snapshot import (
    UniverseSnapshot,
    UniverseSnapshotError,
    load_default_universe,
)


def prepare_production_automatic_selection(
    request: AutomaticSelectionRequest,
) -> AutomaticSelectionResult:
    config = request.config
    market_data = request.market_data
    paths = request.paths
    now = request.now
    started = time.monotonic()
    audit = AuditLogger(paths.audit_log_path)
    try:
        snapshot = load_default_universe()
    except UniverseSnapshotError as exc:
        report = blocked_selection_report_without_snapshot(exc.reason)
        _audit_selection_result(audit, report, started)
        return AutomaticSelectionResult(report, {})
    _audit_universe(audit, snapshot, started)
    resolution = resolve_strategy(config.mode, paths)
    if config.mode == "live" or isinstance(resolution, StrategyResolutionBlock):
        result = prepare_automatic_selection(request)
        _audit_shortlist(audit, result.report, started)
        _audit_selection_result(audit, result.report, started)
        return result
    identity = _cache_identity(request, snapshot, resolution)
    cache = SelectionCache(
        application_data_root() / "auto_selection" / "latest.json",
        ttl=timedelta(minutes=15),
    )
    cached = None if request.daily_forced_order_enabled else cache.read(identity, now)
    if cached is not None:
        risk_limits = resolve_automatic_risk_limits(paths, resolution)
        cached_result = (
            None
            if isinstance(risk_limits, AutomaticRiskBlock)
            else _cached_selection_result(request, cached, risk_limits)
        )
        if cached_result is not None:
            _audit_cache_hit(audit, cached, started)
            _audit_selection_result(audit, cached, started)
            return cached_result
    result = prepare_automatic_selection(request)
    if (
        not request.daily_forced_order_enabled
        and result.report.status in ("selected", "no_trade")
    ):
        cache.write(identity, result.report, now)
    _audit_shortlist(audit, result.report, started)
    _audit_selection_result(audit, result.report, started)
    return result


def _cache_identity(
    request: AutomaticSelectionRequest,
    snapshot: UniverseSnapshot,
    resolved: ResolvedStrategy,
) -> SelectionCacheIdentity:
    config = request.config
    return SelectionCacheIdentity(
        provider=config.broker,
        mode=config.mode,
        universe_id=snapshot.universe_id,
        universe_version=snapshot.checksum,
        universe_effective_date=snapshot.effective_date.isoformat(),
        strategy_id=resolved.spec.strategy_id,
        strategy_version=resolved.spec.version,
        strategy_digest=resolved.spec_digest,
        registry_digest=_file_digest(request.paths.registry_path),
        promoted_digest=_file_digest(request.paths.promoted_path),
        market_date=request.now.date().isoformat(),
        shortlist_limit=30,
    )


def _cached_selection_result(
    request: AutomaticSelectionRequest,
    report: SelectionReport,
    risk_limits,
) -> AutomaticSelectionResult | None:
    config = request.config
    symbols = [item.symbol for item in report.ranked]
    if not symbols:
        return AutomaticSelectionResult(report, {}, risk_limits)
    try:
        legacy_bars = _load_bars(request, symbols)
        quotes = _load_quotes(request, symbols)
    except BrokerRequestError:
        return None
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
        now=request.now,
        quotes_required=config.mode != "dry_run",
    )
    if set(quality.symbols) != set(symbols):
        return None
    return AutomaticSelectionResult(report, legacy_bars, risk_limits, quotes)


def _file_digest(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(payload).hexdigest()


def _audit_universe(
    audit: AuditLogger,
    snapshot: UniverseSnapshot,
    started: float,
) -> None:
    audit.append(
        AuditEvent(
            "universe_loaded",
            payload={
                "universe_id": snapshot.universe_id,
                "effective_date": snapshot.effective_date.isoformat(),
                "symbol_count": len(snapshot.symbols),
                "elapsed_milliseconds": _elapsed_milliseconds(started),
            },
        )
    )


def _audit_cache_hit(
    audit: AuditLogger,
    report: SelectionReport,
    started: float,
) -> None:
    audit.append(
        AuditEvent(
            "selection_cache_used",
            strategy_id=report.strategy_id,
            strategy_version=report.strategy_version,
            payload={
                "selected_count": len(report.selected_symbols),
                "elapsed_milliseconds": _elapsed_milliseconds(started),
            },
        )
    )


def _audit_selection_result(
    audit: AuditLogger,
    report: SelectionReport,
    started: float,
) -> None:
    blocked = report.status == "blocked"
    audit.append(
        AuditEvent(
            "selection_blocked" if blocked else "selection_completed",
            strategy_id=report.strategy_id or None,
            strategy_version=report.strategy_version or None,
            payload={
                "status": report.status,
                "selected_count": len(report.selected_symbols),
                "reason": report.blocked_reasons[0]
                if report.blocked_reasons
                else "",
                "elapsed_milliseconds": _elapsed_milliseconds(started),
            },
        )
    )


def _audit_shortlist(
    audit: AuditLogger,
    report: SelectionReport,
    started: float,
) -> None:
    audit.append(
        AuditEvent(
            "liquidity_shortlist_created",
            strategy_id=report.strategy_id or None,
            strategy_version=report.strategy_version or None,
            payload={
                "shortlist_count": report.shortlist_count,
                "elapsed_milliseconds": _elapsed_milliseconds(started),
            },
        )
    )


def _elapsed_milliseconds(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)
