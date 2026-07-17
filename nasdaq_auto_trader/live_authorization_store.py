from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from .ai_quant_lab.types import JsonObject, JsonValue
from .file_lock import FileLockTimeout, exclusive_file_lock
from .live_authorization import LiveAuthorizationEnvelope


@dataclass(frozen=True, slots=True)
class LiveAuthorizationStoreError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class StoredLiveAuthorization:
    envelope: LiveAuthorizationEnvelope
    cycles: int = 0


class LiveAuthorizationStore:
    def __init__(self, path: Path, lock_timeout_seconds: float = 2.0) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self.lock_timeout_seconds = lock_timeout_seconds

    def load_or_create(
        self,
        envelope: LiveAuthorizationEnvelope,
    ) -> StoredLiveAuthorization:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                stored = self._read_unlocked()
                if stored is not None:
                    return stored
                created = StoredLiveAuthorization(envelope)
                self._write_unlocked(created)
                return created
        except FileLockTimeout as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_lock_timeout"
            ) from exc

    def consume_cycle(
        self,
        expected: LiveAuthorizationEnvelope,
        now: datetime,
    ) -> tuple[str, int]:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                stored = self._read_unlocked()
                if stored is None:
                    return "live_authorization_required", 0
                if stored.envelope != expected:
                    return "live_authorization_binding_changed", stored.cycles
                if now >= stored.envelope.expires_at:
                    return "live_authorization_expired", stored.cycles
                if stored.cycles >= stored.envelope.max_cycles:
                    return "live_authorization_cycle_limit_reached", stored.cycles
                consumed = replace(stored, cycles=stored.cycles + 1)
                self._write_unlocked(consumed)
                return "", consumed.cycles
        except FileLockTimeout as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_lock_timeout"
            ) from exc

    def clear(self) -> None:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                self.path.unlink(missing_ok=True)
        except FileLockTimeout as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_lock_timeout"
            ) from exc
        except OSError as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_write_failed"
            ) from exc

    def _read_unlocked(self) -> StoredLiveAuthorization | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_corrupt"
            ) from exc
        if not isinstance(payload, dict):
            raise LiveAuthorizationStoreError("live_authorization_store_corrupt")
        return _parse_stored_authorization(payload)

    def _write_unlocked(self, stored: StoredLiveAuthorization) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as output:
                json.dump(
                    _stored_authorization_payload(stored),
                    output,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_write_failed"
            ) from exc


def _parse_stored_authorization(payload: JsonObject) -> StoredLiveAuthorization:
    try:
        if payload.get("schema_version") != 1:
            raise LiveAuthorizationStoreError("live_authorization_store_corrupt")
        raw_envelope = payload.get("envelope")
        if not isinstance(raw_envelope, dict):
            raise LiveAuthorizationStoreError("live_authorization_store_corrupt")
        expires_at = datetime.fromisoformat(_required_text(raw_envelope.get("expires_at")))
        if expires_at.tzinfo is None:
            raise LiveAuthorizationStoreError("live_authorization_store_corrupt")
        max_cycles = _required_int(raw_envelope.get("max_cycles"), minimum=1)
        cycles = _required_int(payload.get("cycles"), minimum=0)
        if cycles > max_cycles:
            raise LiveAuthorizationStoreError("live_authorization_store_corrupt")
        envelope = LiveAuthorizationEnvelope(
            strategy_id=_required_text(raw_envelope.get("strategy_id")),
            strategy_version=_required_text(raw_envelope.get("strategy_version")),
            strategy_digest=_required_text(raw_envelope.get("strategy_digest")),
            universe_id=_required_text(raw_envelope.get("universe_id")),
            universe_effective_date=_required_text(
                raw_envelope.get("universe_effective_date")
            ),
            universe_version=_required_text(raw_envelope.get("universe_version")),
            risk_digest=_required_text(raw_envelope.get("risk_digest")),
            mode=_required_text(raw_envelope.get("mode")),
            expires_at=expires_at,
            max_cycles=max_cycles,
            learned_risk_digest=_required_text(
                raw_envelope.get("learned_risk_digest")
            ),
        )
        return StoredLiveAuthorization(envelope, cycles)
    except (TypeError, ValueError) as exc:
        raise LiveAuthorizationStoreError(
            "live_authorization_store_corrupt"
        ) from exc


def _stored_authorization_payload(stored: StoredLiveAuthorization) -> JsonObject:
    envelope = stored.envelope
    return {
        "schema_version": 1,
        "cycles": stored.cycles,
        "envelope": {
            "strategy_id": envelope.strategy_id,
            "strategy_version": envelope.strategy_version,
            "strategy_digest": envelope.strategy_digest,
            "universe_id": envelope.universe_id,
            "universe_effective_date": envelope.universe_effective_date,
            "universe_version": envelope.universe_version,
            "risk_digest": envelope.risk_digest,
            "mode": envelope.mode,
            "expires_at": envelope.expires_at.isoformat(),
            "max_cycles": envelope.max_cycles,
            "learned_risk_digest": envelope.learned_risk_digest,
        },
    }


def _required_text(value: JsonValue) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveAuthorizationStoreError("live_authorization_store_corrupt")
    return value.strip()


def _required_int(value: JsonValue, *, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise LiveAuthorizationStoreError("live_authorization_store_corrupt")
    return value
