from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import math
from pathlib import Path

from nasdaq_auto_trader.config_types import RunMode
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject

from .symbol_selector import RankedSymbol, SelectionReport
from .universe_snapshot import UniverseSnapshotError, load_default_universe


@dataclass(frozen=True, slots=True)
class SelectionCacheIdentity:
    provider: str
    mode: RunMode
    universe_id: str
    universe_version: str
    universe_effective_date: str
    strategy_id: str
    strategy_version: str
    strategy_digest: str
    registry_digest: str
    promoted_digest: str
    market_date: str
    shortlist_limit: int


class SelectionCache:
    def __init__(self, path: Path, ttl: timedelta) -> None:
        self.path = path
        self.ttl = ttl

    def write(
        self,
        identity: SelectionCacheIdentity,
        report: SelectionReport,
        now: datetime,
    ) -> None:
        if identity.mode == "live":
            return
        payload = {
            "written_at": now.isoformat(),
            "identity": asdict(identity),
            "report": _report_to_json(report),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def read(
        self,
        identity: SelectionCacheIdentity,
        now: datetime,
        *,
        mode: RunMode | None = None,
    ) -> SelectionReport | None:
        effective_mode = identity.mode if mode is None else mode
        if effective_mode == "live" or not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            written_at = datetime.fromisoformat(str(payload.get("written_at", "")))
            if now - written_at > self.ttl or now < written_at:
                return None
            if payload.get("identity") != asdict(identity):
                return None
            report = payload.get("report")
            parsed = _report_from_json(report) if isinstance(report, dict) else None
            return parsed if _report_matches_identity(parsed, identity) else None
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            return None


def _report_to_json(report: SelectionReport) -> JsonObject:
    return {
        "status": report.status,
        "universe_id": report.universe_id,
        "universe_effective_date": report.universe_effective_date,
        "universe_version": report.universe_version,
        "strategy_id": report.strategy_id,
        "strategy_version": report.strategy_version,
        "strategy_digest": report.strategy_digest,
        "shortlist_count": report.shortlist_count,
        "ranked": [asdict(item) for item in report.ranked],
        "selected_symbols": list(report.selected_symbols),
        "warnings": list(report.warnings),
        "blocked_reasons": list(report.blocked_reasons),
        "submitted_order": False,
    }


def _report_from_json(payload: dict) -> SelectionReport | None:
    status = payload.get("status")
    if status not in ("selected", "no_trade", "blocked"):
        return None
    ranked_payload = payload.get("ranked")
    if not isinstance(ranked_payload, list):
        return None
    ranked: list[RankedSymbol] = []
    for item in ranked_payload:
        if not isinstance(item, dict):
            return None
        reasons = item.get("reasons")
        if not isinstance(reasons, list):
            return None
        ranked.append(
            RankedSymbol(
                symbol=str(item.get("symbol", "")),
                score=float(item.get("score", 0.0)),
                confidence=float(item.get("confidence", 0.0)),
                reasons=tuple(str(reason) for reason in reasons),
            )
        )
    selected = payload.get("selected_symbols")
    warnings = payload.get("warnings")
    blocked = payload.get("blocked_reasons")
    if not all(isinstance(value, list) for value in (selected, warnings, blocked)):
        return None
    report = SelectionReport(
        status=status,
        universe_id=str(payload.get("universe_id", "")),
        universe_effective_date=str(payload.get("universe_effective_date", "")),
        strategy_id=str(payload.get("strategy_id", "")),
        strategy_version=str(payload.get("strategy_version", "")),
        strategy_digest=str(payload.get("strategy_digest", "")),
        shortlist_count=int(payload.get("shortlist_count", 0)),
        ranked=tuple(ranked),
        selected_symbols=tuple(str(item) for item in selected),
        warnings=tuple(str(item) for item in warnings),
        blocked_reasons=tuple(str(item) for item in blocked),
        submitted_order=False,
        universe_version=str(payload.get("universe_version", "")),
    )
    ranked_symbols = tuple(item.symbol for item in report.ranked)
    if (
        len(set(ranked_symbols)) != len(ranked_symbols)
        or len(set(report.selected_symbols)) != len(report.selected_symbols)
        or not set(report.selected_symbols).issubset(ranked_symbols)
        or any(not item.symbol for item in report.ranked)
        or any(
            not math.isfinite(item.score) or not math.isfinite(item.confidence)
            for item in report.ranked
        )
    ):
        return None
    return report


def _report_matches_identity(
    report: SelectionReport | None,
    identity: SelectionCacheIdentity,
) -> bool:
    if report is None:
        return False
    if not (
        report.universe_id == identity.universe_id
        and report.universe_version == identity.universe_version
        and report.universe_effective_date == identity.universe_effective_date
        and report.strategy_id == identity.strategy_id
        and report.strategy_version == identity.strategy_version
        and report.strategy_digest == identity.strategy_digest
    ):
        return False
    try:
        snapshot = load_default_universe()
    except UniverseSnapshotError:
        return False
    members = {item.symbol for item in snapshot.symbols}
    report_symbols = {
        *(item.symbol for item in report.ranked),
        *report.selected_symbols,
    }
    return report_symbols <= members
