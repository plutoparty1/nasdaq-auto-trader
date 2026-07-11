from __future__ import annotations

from inspect import Parameter, signature

from .engine_types import DecisionPayload
from .models import TradeDecision


def decision_to_dict(decision: TradeDecision) -> DecisionPayload:
    """Convert a strategy decision into JSON-safe CLI output."""

    return {
        "symbol": decision.symbol,
        "action": decision.action,
        "score": decision.score,
        "latest_price": decision.latest_price,
        "reasons": decision.reasons,
        "risk_per_share": decision.risk_per_share,
    }


def _call_with_optional_refresh(loader, refresh: bool):
    """Call broker loaders with refresh=True only when they support it."""

    if refresh and _accepts_refresh_keyword(loader):
        return loader(refresh=True)
    return loader()


def _accepts_refresh_keyword(loader) -> bool:
    try:
        parameters = signature(loader).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "refresh" or parameter.kind == Parameter.VAR_KEYWORD
        for parameter in parameters
    )
