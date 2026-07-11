from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.registry_models import StrategyRecord, StrategyStatus
from nasdaq_auto_trader.ai_quant_lab.storage import safe_artifact_path
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import (
    StrategySpec,
    parse_strategy_spec_json,
)
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject, JsonValue
from nasdaq_auto_trader.config_types import RunMode
from nasdaq_auto_trader.strategies.strategy_library import build_strategy

from .features import PriceBar, calculate_feature_rows
from .universe_snapshot import UniverseSnapshot


SelectionStatus: TypeAlias = Literal["selected", "no_trade", "blocked"]
PAPER_ELIGIBLE = frozenset(
    {
        StrategyStatus.PAPER_CANDIDATE,
        StrategyStatus.PAPER_TRADING,
        StrategyStatus.SHADOW_LIVE,
        StrategyStatus.CHAMPION,
    }
)
MIN_FEATURE_BARS = 20


@dataclass(frozen=True, slots=True)
class StrategyResolutionBlock:
    reason: str


@dataclass(frozen=True, slots=True)
class ResolvedStrategy:
    spec: StrategySpec
    spec_digest: str
    registry_status: StrategyStatus


StrategyResolution: TypeAlias = ResolvedStrategy | StrategyResolutionBlock


@dataclass(frozen=True, slots=True)
class RankedSymbol:
    symbol: str
    score: float
    confidence: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectionReport:
    status: SelectionStatus
    universe_id: str
    universe_effective_date: str
    strategy_id: str
    strategy_version: str
    strategy_digest: str
    shortlist_count: int
    ranked: tuple[RankedSymbol, ...]
    selected_symbols: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    submitted_order: bool = False
    universe_version: str = ""


def resolve_strategy(mode: RunMode, paths: StrategyArtifactPaths) -> StrategyResolution:
    promoted = _load_json_object(paths.promoted_path)
    if promoted is not None and (
        promoted.get("status") == StrategyStatus.ROLLBACK.value
        or promoted.get("mode") == "no_trade"
    ):
        return StrategyResolutionBlock("promoted_strategy_rollback")
    if mode == "live":
        return _resolve_live(promoted, paths)
    return _resolve_nonlive(paths)


def select_symbols(
    snapshot: UniverseSnapshot,
    resolved: ResolvedStrategy,
    bars_by_symbol: dict[str, list[PriceBar]],
    warnings: tuple[str, ...] = (),
) -> SelectionReport:
    members = {item.symbol for item in snapshot.symbols}
    normalized = {
        symbol: bars_by_symbol[symbol]
        for symbol in sorted(bars_by_symbol)
        if symbol in members and len(bars_by_symbol[symbol]) >= MIN_FEATURE_BARS
    }
    if not normalized:
        return _blocked_report(snapshot, resolved, "market_data_incomplete", warnings)
    features = calculate_feature_rows(normalized)
    strategy = build_strategy(resolved.spec)
    ranked_signals = strategy.rank_and_select(strategy.generate_signals(features))
    ranked = tuple(
        RankedSymbol(
            signal.symbol,
            signal.score,
            signal.confidence,
            signal.reasons,
        )
        for signal in ranked_signals
    )
    selected_symbols = tuple(item.symbol for item in ranked)
    status: SelectionStatus = "selected" if selected_symbols else "no_trade"
    return SelectionReport(
        status=status,
        universe_id=snapshot.universe_id,
        universe_effective_date=snapshot.effective_date.isoformat(),
        strategy_id=resolved.spec.strategy_id,
        strategy_version=resolved.spec.version,
        strategy_digest=resolved.spec_digest,
        shortlist_count=len(normalized),
        ranked=ranked,
        selected_symbols=selected_symbols,
        warnings=warnings,
        universe_version=snapshot.checksum,
    )


def blocked_selection_report(
    snapshot: UniverseSnapshot,
    reason: str,
    resolved: ResolvedStrategy | None = None,
    warnings: tuple[str, ...] = (),
) -> SelectionReport:
    return SelectionReport(
        status="blocked",
        universe_id=snapshot.universe_id,
        universe_effective_date=snapshot.effective_date.isoformat(),
        strategy_id=resolved.spec.strategy_id if resolved is not None else "",
        strategy_version=resolved.spec.version if resolved is not None else "",
        strategy_digest=resolved.spec_digest if resolved is not None else "",
        shortlist_count=0,
        ranked=(),
        selected_symbols=(),
        warnings=warnings,
        blocked_reasons=(reason,),
        universe_version=snapshot.checksum,
    )


def blocked_selection_report_without_snapshot(reason: str) -> SelectionReport:
    return SelectionReport(
        status="blocked",
        universe_id="",
        universe_effective_date="",
        strategy_id="",
        strategy_version="",
        strategy_digest="",
        shortlist_count=0,
        ranked=(),
        selected_symbols=(),
        blocked_reasons=(reason,),
    )
def _resolve_nonlive(paths: StrategyArtifactPaths) -> StrategyResolution:
    registry = StrategyRegistry(paths.registry_path, paths.promoted_path)
    records = tuple(
        record
        for record in registry.load_records()
        if record.status in PAPER_ELIGIBLE and math.isfinite(record.score)
    )
    ordered = sorted(records, key=lambda item: (-item.score, item.strategy_id, item.version))
    for record in ordered:
        resolved = _resolved_record(record, paths)
        if resolved is not None:
            return resolved
    return StrategyResolutionBlock("eligible_strategy_unavailable")


def _resolve_live(
    promoted: JsonObject | None,
    paths: StrategyArtifactPaths,
) -> StrategyResolution:
    if promoted is None:
        return StrategyResolutionBlock("promoted_strategy_missing")
    if promoted.get("status") != StrategyStatus.CHAMPION.value:
        return StrategyResolutionBlock("promoted_strategy_not_champion")
    if promoted.get("manual_approval") is not True:
        return StrategyResolutionBlock("manual_approval_missing")
    if promoted.get("allowed_for_live") is not True:
        return StrategyResolutionBlock("promoted_strategy_not_allowed_for_live")
    strategy_id = _text(promoted.get("active_strategy_id"))
    version = _text(promoted.get("strategy_version"))
    spec = _load_spec(paths, strategy_id, version)
    if spec is None:
        return StrategyResolutionBlock("strategy_spec_missing_or_invalid")
    return ResolvedStrategy(spec, _spec_digest(spec), StrategyStatus.CHAMPION)


def _resolved_record(
    record: StrategyRecord,
    paths: StrategyArtifactPaths,
) -> ResolvedStrategy | None:
    spec = _load_spec(paths, record.strategy_id, record.version)
    if spec is None:
        return None
    return ResolvedStrategy(spec, _spec_digest(spec), record.status)


def _load_spec(
    paths: StrategyArtifactPaths,
    strategy_id: str,
    version: str,
) -> StrategySpec | None:
    if not strategy_id or not version:
        return None
    try:
        path = safe_artifact_path(paths.spec_dir, f"{strategy_id}-{version}", ".json")
        validation = parse_strategy_spec_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    spec = validation.spec
    if spec is None or spec.strategy_id != strategy_id or spec.version != version:
        return None
    return spec


def _load_json_object(path: Path) -> JsonObject | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _spec_digest(spec: StrategySpec) -> str:
    canonical = json.dumps(spec.raw, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _blocked_report(
    snapshot: UniverseSnapshot,
    resolved: ResolvedStrategy,
    reason: str,
    warnings: tuple[str, ...],
) -> SelectionReport:
    return blocked_selection_report(snapshot, reason, resolved, warnings)


def _text(value: JsonValue | None) -> str:
    return value.strip() if isinstance(value, str) else ""
