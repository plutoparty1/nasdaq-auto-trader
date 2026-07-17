from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import TypeAlias

from .config import AppConfig
from .live_canary_admin import (
    ArmIssueRequest,
    enforce_private_windows_acl,
    issue_arm,
    windows_sid_sha256,
)
from .live_canary_identity import runtime_identity_path
from .live_canary_paths import CanaryPaths
from .live_canary_policy import CANARY_POLICY
from .live_canary_preflight import (
    KISPreflightTransportClient,
    ReadOnlyPreflightClient,
    run_preflight,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class LiveCanaryCliError(ValueError):
    pass


def run_canary_preflight(config: AppConfig) -> dict[str, JsonValue]:
    client = _real_read_client(config)
    result = run_preflight(client)
    return {
        "ready": result.ready,
        "cash_gate_met": result.cash_gate_met,
        "position_count": result.position_count,
        "open_order_count": result.open_order_count,
        "blockers": list(result.blockers),
        "transport": "trading API GET-only (OAuth token acquisition may POST)",
        "submitted_order": False,
    }


def run_canary_arm(
    config: AppConfig,
    market_date: str,
    confirmation: str,
) -> dict[str, JsonValue]:
    now = datetime.now(UTC)
    paths = CanaryPaths.for_market_date(market_date)
    result = issue_arm(
        ArmIssueRequest(
            config=config,
            client=_real_read_client(config),
            paths=paths,
            executable=runtime_identity_path(),
            market_date=market_date,
            confirmation=confirmation,
            now=now,
            windows_sid_sha256=windows_sid_sha256(),
        ),
        enforce_acl=enforce_private_windows_acl,
    )
    return {
        "armed": True,
        "market_date": market_date,
        "arm_path": str(result.arm_path),
        "state_path": str(result.state_path),
        "submitted_order": False,
    }


def run_canary_service(
    config: AppConfig,
    max_loops: int | None,
) -> dict[str, JsonValue]:
    from .live_canary_runner import LiveCanaryRunRequest, run_live_canary

    return asdict(run_live_canary(LiveCanaryRunRequest(config, max_loops)))


def _real_read_client(config: AppConfig) -> ReadOnlyPreflightClient:
    if config.broker != "kis":
        raise LiveCanaryCliError("live canary requires broker=kis")
    credentials = replace(
        config.kis,
        paper=False,
        timeout=min(config.kis.timeout, CANARY_POLICY.max_get_timeout_seconds),
    )
    return ReadOnlyPreflightClient(KISPreflightTransportClient(credentials))
