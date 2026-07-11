from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterator

from .file_lock import FileLockTimeout, exclusive_file_lock
from .session_claims import ClaimDecision, ClaimStatus, SignalKey
from .session_safety_policy import SessionSafetyPolicyError, safety_block_reason
from .session_state_codec import (
    ParsedSafetyState,
    SessionStateCodecError,
    parse_claims,
    parse_safety_state,
    parsed_market_date,
    required_market_date,
    validate_safety_state,
)


class SessionStoreError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class PersistedSafetyState:
    market_date: str = ""
    buy_count: int = 0
    sell_count: int = 0
    last_order_at: str = ""
    daily_loss_breached: bool = False
    baseline_observed: bool = False


@dataclass(frozen=True, slots=True)
class SafetyReservationRequest:
    market_date: str
    side: str
    timestamp: str
    max_daily_buy_count: int
    max_daily_sell_count: int
    cooldown_minutes: int
    daily_loss_breached: bool
    daily_loss_state_unavailable: bool
    baseline_available: bool
    max_daily_order_count: int = 2**31 - 1


@dataclass(frozen=True, slots=True)
class SafetyReservationDecision:
    granted: bool
    reason: str = ""


class TradingSessionStore:
    def __init__(self, path: Path, lock_timeout_seconds: float = 2.0) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self.lock_timeout_seconds = lock_timeout_seconds

    def claim(self, key: SignalKey) -> ClaimDecision:
        with self._locked():
            safety, claims = self._read_unlocked()
            digest = key.digest()
            existing = claims.get(digest)
            if existing is not None:
                return ClaimDecision(False, f"signal_key_{existing.value}", existing)
            claims[digest] = ClaimStatus.SUBMITTING
            self._write_unlocked(safety, claims)
            return ClaimDecision(True, "", ClaimStatus.SUBMITTING)

    def reserve_safety(
        self,
        request: SafetyReservationRequest,
    ) -> SafetyReservationDecision:
        with self._locked():
            safety, claims = self._read_unlocked()
            try:
                persisted_date = parsed_market_date(safety.market_date)
                requested_date = required_market_date(request.market_date)
            except SessionStateCodecError as exc:
                raise SessionStoreError("session_store_corrupt") from exc
            if persisted_date is not None and requested_date < persisted_date:
                return SafetyReservationDecision(
                    False,
                    "session_market_date_regression",
                )
            if persisted_date != requested_date:
                safety = PersistedSafetyState(market_date=request.market_date)
            if request.daily_loss_breached and not safety.daily_loss_breached:
                safety = replace(
                    safety,
                    daily_loss_breached=True,
                    baseline_observed=True,
                )
                self._write_unlocked(safety, claims)
            try:
                reason = safety_block_reason(safety, request)
            except SessionSafetyPolicyError as exc:
                raise SessionStoreError("session_store_corrupt") from exc
            if reason:
                return SafetyReservationDecision(False, reason)
            reserved = replace(
                safety,
                buy_count=safety.buy_count + (1 if request.side == "buy" else 0),
                sell_count=safety.sell_count + (1 if request.side == "sell" else 0),
                last_order_at=request.timestamp,
                baseline_observed=(
                    safety.baseline_observed or request.baseline_available
                ),
            )
            self._write_unlocked(reserved, claims)
            return SafetyReservationDecision(True)

    def complete(self, key: SignalKey, status: ClaimStatus) -> None:
        if status not in (
            ClaimStatus.SUBMITTED,
            ClaimStatus.REJECTED,
            ClaimStatus.UNCERTAIN,
        ):
            raise SessionStoreError("claim_terminal_status_invalid")
        with self._locked():
            safety, claims = self._read_unlocked()
            digest = key.digest()
            if digest not in claims:
                raise SessionStoreError("signal_key_missing")
            claims[digest] = status
            self._write_unlocked(safety, claims)

    def recover_interrupted_claims(self) -> int:
        with self._locked():
            safety, claims = self._read_unlocked()
            interrupted = tuple(
                digest
                for digest, status in claims.items()
                if status is ClaimStatus.SUBMITTING
            )
            for digest in interrupted:
                claims[digest] = ClaimStatus.UNCERTAIN
            if interrupted:
                self._write_unlocked(safety, claims)
            return len(interrupted)

    def save_safety_state(self, state: PersistedSafetyState) -> None:
        with self._locked():
            _, claims = self._read_unlocked()
            _ensure_valid_state(state)
            self._write_unlocked(state, claims)

    def merge_safety_state(self, state: PersistedSafetyState) -> None:
        with self._locked():
            persisted, claims = self._read_unlocked()
            _ensure_valid_state(state)
            try:
                persisted_date = parsed_market_date(persisted.market_date)
                state_date = parsed_market_date(state.market_date)
            except SessionStateCodecError as exc:
                raise SessionStoreError("session_store_corrupt") from exc
            if state_date is None or (
                persisted_date is not None and state_date < persisted_date
            ):
                merged = persisted
            elif persisted_date != state_date:
                merged = state
            else:
                merged = PersistedSafetyState(
                    market_date=state.market_date,
                    buy_count=max(persisted.buy_count, state.buy_count),
                    sell_count=max(persisted.sell_count, state.sell_count),
                    last_order_at=max(
                        persisted.last_order_at,
                        state.last_order_at,
                    ),
                    daily_loss_breached=(
                        persisted.daily_loss_breached
                        or state.daily_loss_breached
                    ),
                    baseline_observed=(
                        persisted.baseline_observed
                        or state.baseline_observed
                    ),
                )
            self._write_unlocked(merged, claims)

    def load_safety_state(self) -> PersistedSafetyState:
        with self._locked():
            safety, _ = self._read_unlocked()
            return safety

    @contextmanager
    def _locked(self) -> Iterator[None]:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                yield
        except FileLockTimeout as exc:
            raise SessionStoreError("session_store_lock_timeout") from exc

    def _read_unlocked(self) -> tuple[PersistedSafetyState, dict[str, ClaimStatus]]:
        if not self.path.exists():
            return PersistedSafetyState(), {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SessionStoreError("session_store_corrupt") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise SessionStoreError("session_store_corrupt")
        raw_safety = payload.get("safety")
        raw_claims = payload.get("claims")
        if not isinstance(raw_safety, dict) or not isinstance(raw_claims, dict):
            raise SessionStoreError("session_store_corrupt")
        try:
            parsed = parse_safety_state(raw_safety)
            safety = PersistedSafetyState(
                parsed.market_date,
                parsed.buy_count,
                parsed.sell_count,
                parsed.last_order_at,
                parsed.daily_loss_breached,
                parsed.baseline_observed,
            )
            claims = {
                digest: ClaimStatus(status)
                for digest, status in parse_claims(raw_claims).items()
            }
        except (SessionStateCodecError, ValueError) as exc:
            raise SessionStoreError("session_store_corrupt") from exc
        return safety, claims

    def _write_unlocked(
        self,
        safety: PersistedSafetyState,
        claims: dict[str, ClaimStatus],
    ) -> None:
        payload = {
            "schema_version": 1,
            "safety": asdict(safety),
            "claims": {digest: status.value for digest, status in claims.items()},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise SessionStoreError("session_store_write_failed") from exc


def _ensure_valid_state(state: PersistedSafetyState) -> None:
    try:
        validate_safety_state(
            ParsedSafetyState(
                state.market_date,
                state.buy_count,
                state.sell_count,
                state.last_order_at,
                state.daily_loss_breached,
                state.baseline_observed,
            )
        )
    except SessionStateCodecError as exc:
        raise SessionStoreError("session_store_corrupt") from exc
