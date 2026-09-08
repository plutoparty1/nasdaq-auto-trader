from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, assert_never

from .ai_quant_lab.artifact_paths import (
    StrategyArtifactPaths,
    default_strategy_artifact_paths,
)
from .ai_quant_lab.audit_logger import AuditEvent, AuditLogger
from .ai_quant_lab.types import JsonObject
from .automatic_order_types import AuditSink
from .config import AppConfig
from .live_authorization import (
    LiveAuthorizationBlock,
    LiveAuthorizationEnvelope,
    LiveAuthorizationRequest,
    create_live_authorization,
)
from .live_authorization_store import (
    LiveAuthorizationStore,
    LiveAuthorizationStoreError,
)
from .quant_data.resources import application_data_root


LIVE_SESSION_CONFIRMATION: Final = (
    "I UNDERSTAND THIS WILL PLACE REAL ORDERS DURING ONE NASDAQ SESSION"
)


@dataclass(frozen=True, slots=True)
class SessionAuthorizationRequest:
    config: AppConfig
    paths: StrategyArtifactPaths
    store: LiveAuthorizationStore
    audit: AuditSink
    now: datetime
    max_attempts: int
    confirmation: str


def authorize_live_session(request: SessionAuthorizationRequest) -> JsonObject:
    if request.confirmation != LIVE_SESSION_CONFIRMATION:
        return _blocked("live_session_confirmation_required")
    config_reason = _live_config_reason(request.config)
    if config_reason:
        return _blocked(config_reason)
    created = create_live_authorization(
        LiveAuthorizationRequest(
            request.config,
            request.paths,
            request.now,
            request.max_attempts,
        )
    )
    match created:
        case LiveAuthorizationBlock(reason=reason):
            return _blocked(reason)
        case LiveAuthorizationEnvelope() as envelope:
            if not request.audit.append(
                AuditEvent(
                    "live_authorization_session_approval_requested",
                    payload={
                        "market_date": envelope.market_date.isoformat(),
                        "max_attempts": envelope.max_attempts,
                    },
                )
            ):
                return _blocked("live_authorization_audit_write_failed")
            try:
                request.store.issue(envelope)
            except LiveAuthorizationStoreError as exc:
                return _blocked(exc.reason)
            completion_recorded = request.audit.append(
                AuditEvent(
                    "live_authorization_session_approved",
                    payload={
                        "market_date": envelope.market_date.isoformat(),
                        "max_attempts": envelope.max_attempts,
                    },
                )
            )
            return {
                "status": "authorized",
                "reason": "",
                "market_date": envelope.market_date.isoformat(),
                "max_attempts": envelope.max_attempts,
                "attempts": 0,
                "audit_completion_recorded": completion_recorded,
                "submitted_order": False,
                "network_client_constructed": False,
            }
        case unreachable:
            assert_never(unreachable)


def revoke_live_session(store: LiveAuthorizationStore, audit: AuditSink) -> JsonObject:
    if not audit.append(AuditEvent("live_authorization_session_revocation_requested")):
        return _blocked("live_authorization_audit_write_failed")
    try:
        cleanup_completed = store.clear(archive=True)
    except LiveAuthorizationStoreError as exc:
        return _blocked(exc.reason)
    completion_recorded = audit.append(
        AuditEvent("live_authorization_session_revoked")
    )
    return {
        "status": "revoked",
        "reason": "",
        "audit_completion_recorded": completion_recorded,
        "revocation_cleanup_completed": cleanup_completed,
        "submitted_order": False,
        "network_client_constructed": False,
    }


def run_default_authorize(
    config: AppConfig,
    max_attempts: int,
    confirmation: str,
) -> JsonObject:
    paths = default_strategy_artifact_paths()
    return authorize_live_session(
        SessionAuthorizationRequest(
            config,
            paths,
            _default_store(),
            AuditLogger(paths.audit_log_path),
            datetime.now(timezone.utc),
            max_attempts,
            confirmation,
        )
    )


def run_default_revoke() -> JsonObject:
    paths = default_strategy_artifact_paths()
    return revoke_live_session(
        _default_store(),
        AuditLogger(paths.audit_log_path),
    )


def _default_store() -> LiveAuthorizationStore:
    return LiveAuthorizationStore(
        application_data_root()
        / "runtime"
        / "trading_session.live-authorization.json"
    )


def _blocked(reason: str) -> JsonObject:
    return {
        "status": "blocked",
        "reason": reason,
        "submitted_order": False,
        "network_client_constructed": False,
    }


def _live_config_reason(config: AppConfig) -> str:
    if config.mode != "live":
        return "live_authorization_live_mode_required"
    if not config.allow_live_trading:
        return "live_trading_disabled"
    if not config.live_environment_authorized:
        return "live_environment_authorization_required"
    match config.broker:
        case "kis":
            paper = config.kis.paper
        case "alpaca":
            paper = config.alpaca.paper
        case unreachable:
            assert_never(unreachable)
    return "live_authorization_real_broker_required" if paper else ""
