from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .ai_quant_lab.types import JsonObject, JsonValue
from .live_authorization import AuthorizationPurpose, LiveAuthorizationEnvelope


@dataclass(frozen=True, slots=True)
class LiveAuthorizationCodecError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class StoredLiveAuthorization:
    envelope: LiveAuthorizationEnvelope
    attempts: int = 0


def parse_stored_authorization(payload: JsonObject) -> StoredLiveAuthorization:
    schema_version = payload.get("schema_version")
    if schema_version == 1:
        raise LiveAuthorizationCodecError(
            "live_authorization_reapproval_required"
        )
    if schema_version != 2:
        raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
    raw_envelope = payload.get("envelope")
    if not isinstance(raw_envelope, dict):
        raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
    try:
        market_date = date.fromisoformat(_required_text(raw_envelope.get("market_date")))
        max_attempts = _required_int(
            raw_envelope.get("max_attempts"),
            minimum=0,
            maximum=12,
        )
        attempts = _required_nonnegative_int(payload.get("attempts"))
        if max_attempts > 0 and attempts > max_attempts:
            raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
        authorization_id = _required_text(raw_envelope.get("authorization_id"))
        if len(authorization_id) != 32:
            raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
        int(authorization_id, 16)
        envelope = LiveAuthorizationEnvelope(
            authorization_id=authorization_id,
            market_date=market_date,
            max_attempts=max_attempts,
            strategy_id=_required_text(raw_envelope.get("strategy_id")),
            strategy_version=_required_text(raw_envelope.get("strategy_version")),
            strategy_digest=_required_text(raw_envelope.get("strategy_digest")),
            universe_id=_required_text(raw_envelope.get("universe_id")),
            universe_effective_date=_required_text(
                raw_envelope.get("universe_effective_date")
            ),
            universe_version=_required_text(raw_envelope.get("universe_version")),
            risk_digest=_required_text(raw_envelope.get("risk_digest")),
            mode=_required_live_mode(raw_envelope.get("mode")),
            learned_risk_digest=_required_text(
                raw_envelope.get("learned_risk_digest")
            ),
            broker_authorization_digest=_required_text(
                raw_envelope.get("broker_authorization_digest")
            ),
            purpose=_authorization_purpose(raw_envelope.get("purpose", "automatic")),
        )
        if envelope.max_attempts == 0 and envelope.purpose != "automatic":
            raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
    except (TypeError, ValueError) as exc:
        raise LiveAuthorizationCodecError(
            "live_authorization_store_corrupt"
        ) from exc
    return StoredLiveAuthorization(envelope, attempts)


def stored_authorization_payload(stored: StoredLiveAuthorization) -> JsonObject:
    envelope = stored.envelope
    return {
        "schema_version": 2,
        "attempts": stored.attempts,
        "envelope": {
            "authorization_id": envelope.authorization_id,
            "market_date": envelope.market_date.isoformat(),
            "max_attempts": envelope.max_attempts,
            "strategy_id": envelope.strategy_id,
            "strategy_version": envelope.strategy_version,
            "strategy_digest": envelope.strategy_digest,
            "universe_id": envelope.universe_id,
            "universe_effective_date": envelope.universe_effective_date,
            "universe_version": envelope.universe_version,
            "risk_digest": envelope.risk_digest,
            "mode": envelope.mode,
            "learned_risk_digest": envelope.learned_risk_digest,
            "broker_authorization_digest": envelope.broker_authorization_digest,
            "purpose": envelope.purpose,
        },
    }


def _required_text(value: JsonValue | None) -> str:
    if not isinstance(value, str) or not value:
        raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
    return value


def _required_int(
    value: JsonValue | None,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
    if value < minimum or value > maximum:
        raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
    return value


def _required_nonnegative_int(value: JsonValue | None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
    return value


def _required_live_mode(value: JsonValue | None) -> str:
    mode = _required_text(value)
    if mode != "live":
        raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
    return mode


def _authorization_purpose(value: JsonValue | None) -> AuthorizationPurpose:
    purpose = _required_text(value)
    if purpose == "automatic":
        return "automatic"
    if purpose == "daily_forced":
        return "daily_forced"
    raise LiveAuthorizationCodecError("live_authorization_store_corrupt")
