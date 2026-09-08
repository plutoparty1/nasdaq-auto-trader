from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Literal, TypeAlias, assert_never

from .ai_quant_lab.artifact_paths import StrategyArtifactPaths
from .automatic_risk_config import (
    AutomaticRiskConfigBlock,
    learned_risk_config_digest,
    load_automatic_risk_config,
)
from .config import AppConfig
from .live_canary_identity import account_fingerprint
from .market_hours import MarketTimeError, authorization_market_date
from .quant_data.symbol_selector import (
    StrategyResolutionBlock,
    resolve_strategy,
)
from .quant_data.universe_snapshot import (
    UniverseSnapshotError,
    load_default_universe,
    universe_freshness,
)


AuthorizationPurpose: TypeAlias = Literal["automatic", "daily_forced"]


@dataclass(frozen=True, slots=True)
class LiveAuthorizationRequest:
    config: AppConfig
    paths: StrategyArtifactPaths
    now: datetime
    max_attempts: int = 12
    purpose: AuthorizationPurpose = "automatic"


@dataclass(frozen=True, slots=True)
class LiveAuthorizationBlock:
    reason: str


@dataclass(frozen=True, slots=True)
class LiveAuthorizationEnvelope:
    authorization_id: str
    market_date: date
    max_attempts: int
    strategy_id: str
    strategy_version: str
    strategy_digest: str
    universe_id: str
    universe_effective_date: str
    universe_version: str
    risk_digest: str
    mode: str
    learned_risk_digest: str
    broker_authorization_digest: str
    purpose: AuthorizationPurpose = "automatic"


def create_live_authorization(
    request: LiveAuthorizationRequest,
) -> LiveAuthorizationEnvelope | LiveAuthorizationBlock:
    unlimited_automatic = (
        request.purpose == "automatic" and request.max_attempts == 0
    )
    if not unlimited_automatic and not 1 <= request.max_attempts <= 12:
        return LiveAuthorizationBlock("live_authorization_attempt_limit_invalid")
    try:
        market_date = authorization_market_date(request.now)
    except MarketTimeError as exc:
        return LiveAuthorizationBlock(exc.reason)
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
        market_date,
    )
    if freshness.blocked_reason:
        return LiveAuthorizationBlock(freshness.blocked_reason)
    return LiveAuthorizationEnvelope(
        authorization_id=secrets.token_hex(16),
        market_date=market_date,
        max_attempts=request.max_attempts,
        strategy_id=resolved.spec.strategy_id,
        strategy_version=resolved.spec.version,
        strategy_digest=resolved.spec_digest,
        universe_id=snapshot.universe_id,
        universe_effective_date=snapshot.effective_date.isoformat(),
        universe_version=snapshot.checksum,
        risk_digest=risk_config_digest(request.config, request.paths),
        mode=request.config.mode,
        learned_risk_digest=learned_risk_config_digest(request.paths.ai_config_path),
        broker_authorization_digest=broker_authorization_digest(request.config),
        purpose=request.purpose,
    )


def broker_authorization_digest(config: AppConfig) -> str:
    match config.broker:
        case "kis":
            identity = {
                "account_fingerprint": account_fingerprint(
                    config.kis.account_no,
                    config.kis.account_product_code,
                ),
                "broker": "kis",
                "currency": config.kis.currency,
                "environment": "paper" if config.kis.paper else "live",
                "order_exchange_code": config.kis.order_exchange_code,
                "price_exchange_code": config.kis.price_exchange_code,
                "product_code": config.kis.account_product_code,
            }
        case "alpaca":
            identity = {
                "broker": "alpaca",
                "credential_fingerprint": hashlib.sha256(
                    config.alpaca.api_key.encode("utf-8")
                ).hexdigest(),
                "environment": "paper" if config.alpaca.paper else "live",
                "feed": config.alpaca.feed,
            }
        case unreachable:
            assert_never(unreachable)
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


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
