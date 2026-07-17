from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ArmEnvelopeError(Exception):
    reason: str

    def __str__(self) -> str:
        return f"invalid live-canary arm envelope: {self.reason}"


@dataclass(frozen=True, slots=True)
class ArmEnvelope:
    schema_version: int
    market_date: str
    account_fingerprint: str
    product: str
    base_url: str
    executable_sha256: str
    policy_digest: str
    windows_sid_sha256: str
    state_nonce: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ArmValidationContext:
    market_date: str
    account_fingerprint: str
    product: str
    base_url: str
    executable_sha256: str
    policy_digest: str
    windows_sid_sha256: str
    now: datetime


def parse_arm_envelope(raw: Mapping[str, str]) -> ArmEnvelope:
    schema_version = _required_int(raw, "schema_version")
    if schema_version != 1:
        raise ArmEnvelopeError("unsupported schema version")
    issued_at = _parse_timestamp(_required_text(raw, "issued_at"), "issued_at")
    expires_at = _parse_timestamp(_required_text(raw, "expires_at"), "expires_at")
    if expires_at <= issued_at:
        raise ArmEnvelopeError("expiry must follow issuance")
    return ArmEnvelope(
        schema_version=schema_version,
        market_date=_required_text(raw, "market_date"),
        account_fingerprint=_required_text(raw, "account_fingerprint"),
        product=_required_text(raw, "product"),
        base_url=_required_text(raw, "base_url"),
        executable_sha256=_sha256(_required_text(raw, "executable_sha256")),
        policy_digest=_sha256(_required_text(raw, "policy_digest")),
        windows_sid_sha256=_sha256(_required_text(raw, "windows_sid_sha256")),
        state_nonce=_required_text(raw, "state_nonce"),
        issued_at=issued_at,
        expires_at=expires_at,
    )


def validate_arm_envelope(envelope: ArmEnvelope, context: ArmValidationContext) -> None:
    if context.now.tzinfo is None:
        raise ArmEnvelopeError("validation clock must be timezone-aware")
    if context.now.astimezone(UTC) >= envelope.expires_at:
        raise ArmEnvelopeError("authorization expired")
    actual = (
        context.market_date,
        context.account_fingerprint,
        context.product,
        context.base_url,
        context.executable_sha256,
        context.policy_digest,
        context.windows_sid_sha256,
    )
    expected = (
        envelope.market_date,
        envelope.account_fingerprint,
        envelope.product,
        envelope.base_url,
        envelope.executable_sha256,
        envelope.policy_digest,
        envelope.windows_sid_sha256,
    )
    if actual != expected:
        raise ArmEnvelopeError("authorization binding mismatch")


def _required_text(raw: Mapping[str, str], field: str) -> str:
    value = raw.get(field)
    if value is None or not value.strip():
        raise ArmEnvelopeError(f"missing {field}")
    return value


def _required_int(raw: Mapping[str, str], field: str) -> int:
    value = _required_text(raw, field)
    try:
        return int(value)
    except ValueError as error:
        raise ArmEnvelopeError(f"invalid {field}") from error


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ArmEnvelopeError(f"invalid {field}") from error
    if parsed.tzinfo is None:
        raise ArmEnvelopeError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ArmEnvelopeError("executable_sha256 must be lowercase SHA-256")
    return value
