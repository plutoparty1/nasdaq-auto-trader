from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from .brokers.kis_client import KISClient
from .config import AppConfig, validate_trading_mode
from .day_trade_types import DEFAULT_DAY_TRADE_CANDIDATES
from .live_canary_arm import (
    ArmEnvelope,
    ArmEnvelopeError,
    ArmValidationContext,
    parse_arm_envelope,
    validate_arm_envelope,
)
from .live_canary_paths import CanaryPaths
from .live_canary_policy import CANARY_POLICY
from .live_canary_state import (
    CanaryState,
    CanaryStateCorruptError,
    CanaryStateStore,
    StateMode,
)
from .quant_data.universe_snapshot import load_default_universe


def expire_state(
    state: CanaryState,
    current_store: CanaryStateStore,
    exit_store: CanaryStateStore,
) -> tuple[CanaryState, bool]:
    if state.owned_symbol is None:
        return state, True
    expired = state.expire_arm()
    current_store.save(expired)
    exit_store.save(expired)
    return expired, False


def load_exit_only_recovery(
    paths: CanaryPaths,
    market_date: str,
    fingerprint: str,
    executable_digest: str,
    sid_digest: str,
) -> CanaryState:
    raw = json.loads(paths.exit_only_state.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("nonce"), str):
        raise CanaryStateCorruptError("exit-only recovery state is invalid")
    state = CanaryStateStore(paths.exit_only_state).load(expected_nonce=raw["nonce"])
    if state.mode is not StateMode.EXIT_ONLY or state.owned_symbol is None:
        raise CanaryStateCorruptError("exit-only recovery has no owned exposure")
    if (state.account_fingerprint, state.executable_sha256) != (
        fingerprint,
        executable_digest,
    ):
        raise CanaryStateCorruptError("exit-only recovery binding mismatch")
    _validate_original_arm(paths, state, fingerprint, executable_digest, sid_digest)
    if state.market_date < market_date:
        return state.for_next_session(market_date)
    if state.market_date != market_date:
        raise CanaryStateCorruptError("exit-only recovery market date is invalid")
    return state


def recovery_envelope(
    state: CanaryState,
    sid_digest: str,
    now: datetime,
) -> ArmEnvelope:
    return ArmEnvelope(
        1,
        state.market_date,
        state.account_fingerprint,
        "kis-real",
        KISClient.real_base_url,
        state.executable_sha256,
        CANARY_POLICY.digest,
        sid_digest,
        state.nonce,
        now,
        now + timedelta(days=1),
    )


def load_envelope(path: Path) -> ArmEnvelope:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw.items()
    ):
        raise ArmEnvelopeError("arm payload must be a string mapping")
    return parse_arm_envelope(raw)


def validate_envelope(
    envelope: ArmEnvelope,
    context: ArmValidationContext,
) -> None:
    validation_clock = context.now if context.now < envelope.expires_at else envelope.issued_at
    validate_arm_envelope(envelope, replace(context, now=validation_clock))


def config_error(config: AppConfig) -> str:
    try:
        validate_trading_mode(config)
    except ValueError as error:
        return str(error)
    if (
        config.broker != "kis"
        or config.mode != "live"
        or config.kis.paper
        or config.kis.currency.upper() != "USD"
    ):
        return "live_real_kis_usd_configuration_required"
    return ""


def canary_universe(configured: list[str]) -> frozenset[str]:
    snapshot = load_default_universe()
    return frozenset(
        [
            *configured,
            *DEFAULT_DAY_TRADE_CANDIDATES,
            *(item.symbol for item in snapshot.symbols),
        ]
    )


def _validate_original_arm(
    paths: CanaryPaths,
    state: CanaryState,
    fingerprint: str,
    executable_digest: str,
    sid_digest: str,
) -> None:
    original_arm = load_envelope(CanaryPaths(paths.root, state.market_date).arm)
    actual = (
        original_arm.market_date,
        original_arm.state_nonce,
        original_arm.account_fingerprint,
        original_arm.product,
        original_arm.base_url,
        original_arm.executable_sha256,
        original_arm.policy_digest,
        original_arm.windows_sid_sha256,
    )
    expected = (
        state.market_date,
        state.nonce,
        fingerprint,
        "kis-real",
        KISClient.real_base_url,
        executable_digest,
        CANARY_POLICY.digest,
        sid_digest,
    )
    if actual != expected:
        raise CanaryStateCorruptError("exit-only original arm binding mismatch")
