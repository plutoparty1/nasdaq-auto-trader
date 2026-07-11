from __future__ import annotations

from datetime import datetime

from .ai_quant_lab.artifact_paths import StrategyArtifactPaths
from .automatic_order_types import AutomaticOrderContext, strategy_mismatch
from .automatic_risk_config import learned_risk_config_digest
from .market_hours import EASTERN
from .quant_data.symbol_selector import StrategyResolutionBlock, resolve_strategy
from .quant_data.universe_snapshot import (
    UniverseSnapshotError,
    load_default_universe,
    universe_freshness,
)


def live_readiness_reason(
    context: AutomaticOrderContext,
    paths: StrategyArtifactPaths,
    now: datetime,
) -> str:
    resolved = resolve_strategy("live", paths)
    if isinstance(resolved, StrategyResolutionBlock):
        return resolved.reason
    mismatch = strategy_mismatch(context, resolved)
    if mismatch:
        return mismatch
    if context.learned_risk_digest != learned_risk_config_digest(
        paths.ai_config_path
    ):
        return "live_authorization_binding_changed"
    try:
        snapshot = load_default_universe()
    except UniverseSnapshotError as exc:
        return exc.reason
    freshness = universe_freshness(
        snapshot,
        "live",
        now.astimezone(EASTERN).date(),
    )
    if freshness.blocked_reason:
        return freshness.blocked_reason
    bindings_match = (
        context.universe_id == snapshot.universe_id
        and context.universe_effective_date == snapshot.effective_date.isoformat()
        and context.universe_version == snapshot.checksum
    )
    return "" if bindings_match else "live_authorization_binding_changed"
