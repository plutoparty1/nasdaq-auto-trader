from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from .ai_quant_lab.artifact_paths import StrategyArtifactPaths
from .automatic_risk_config import (
    AutomaticRiskConfigBlock,
    learned_risk_config_digest,
    load_automatic_risk_config,
)
from .config import AppConfig
from .quant_data.symbol_selector import (
    StrategyResolutionBlock,
    resolve_strategy,
)
from .quant_data.universe_snapshot import (
    UniverseSnapshotError,
    load_default_universe,
    universe_freshness,
)
from .market_hours import EASTERN


@dataclass(frozen=True, slots=True)
class LiveAuthorizationRequest:
    config: AppConfig
    paths: StrategyArtifactPaths
    now: datetime
    duration_minutes: int
    max_cycles: int


@dataclass(frozen=True, slots=True)
class LiveAuthorizationBlock:
    reason: str


@dataclass(frozen=True, slots=True)
class LiveAuthorizationEnvelope:
    strategy_id: str
    strategy_version: str
    strategy_digest: str
    universe_id: str
    universe_effective_date: str
    universe_version: str
    risk_digest: str
    mode: str
    expires_at: datetime
    max_cycles: int
    learned_risk_digest: str


def create_live_authorization(
    request: LiveAuthorizationRequest,
) -> LiveAuthorizationEnvelope | LiveAuthorizationBlock:
    if not 1 <= request.duration_minutes <= 60:
        return LiveAuthorizationBlock("live_authorization_duration_invalid")
    if not 1 <= request.max_cycles <= 12:
        return LiveAuthorizationBlock("live_authorization_cycle_limit_invalid")
    resolved = resolve_strategy("live", request.paths)
    if isinstance(resolved, StrategyResolutionBlock):
        return LiveAuthorizationBlock(resolved.reason)
    try:
        snapshot = load_default_universe()
    except UniverseSnapshotError as exc:
        return LiveAuthorizationBlock(exc.reason)
    freshness = universe_freshness(
        snapshot,
        "live",
        request.now.astimezone(EASTERN).date(),
    )
    if freshness.blocked_reason:
        return LiveAuthorizationBlock(freshness.blocked_reason)
    return LiveAuthorizationEnvelope(
        strategy_id=resolved.spec.strategy_id,
        strategy_version=resolved.spec.version,
        strategy_digest=resolved.spec_digest,
        universe_id=snapshot.universe_id,
        universe_effective_date=snapshot.effective_date.isoformat(),
        universe_version=snapshot.checksum,
        risk_digest=risk_config_digest(request.config, request.paths),
        mode=request.config.mode,
        expires_at=request.now + timedelta(minutes=request.duration_minutes),
        max_cycles=request.max_cycles,
        learned_risk_digest=learned_risk_config_digest(request.paths.ai_config_path),
    )


def risk_config_digest(
    config: AppConfig,
    paths: StrategyArtifactPaths | None = None,
) -> str:
    loaded = load_automatic_risk_config(
        paths.ai_config_path if paths is not None else None
    )
    ai_config = (
        loaded.to_json_object()
        if not isinstance(loaded, AutomaticRiskConfigBlock)
        else {"status": "invalid"}
    )
    payload = json.dumps(
        {
            "application": asdict(config.risk),
            "learned": ai_config,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()
