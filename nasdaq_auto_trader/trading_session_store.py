from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .file_lock import FileLockTimeout, exclusive_file_lock
from .session_claims import ClaimDecision, ClaimRecord, ClaimStatus, SignalKey
from .session_safety_merge import merge_persisted_safety_state
from .session_safety_reservation import (
    PersistedSafetyState,
    SafetyReservationDecision,
    SafetyReservationError,
    SafetyReservationRequest,
    reserve_safety_state,
)
from .session_store_io import (
    SessionPayloadError,
    read_session_payload,
    write_session_payload,
)
from .session_state_codec import (
    ParsedSafetyState,
    SessionStateCodecError,
    validate_safety_state,
)


class SessionStoreError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


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
                return ClaimDecision(
                    False,
                    f"signal_key_{existing.status.value}",
                    existing.status,
                )
            claims[digest] = ClaimRecord(ClaimStatus.SUBMITTING, key.market_date)
            self._write_unlocked(safety, claims)
            return ClaimDecision(True, "", ClaimStatus.SUBMITTING)

    def reserve_safety(
        self,
        request: SafetyReservationRequest,
    ) -> SafetyReservationDecision:
        with self._locked():
            safety, claims = self._read_unlocked()
            try:
                updated, decision = reserve_safety_state(safety, request)
            except SafetyReservationError as exc:
                raise SessionStoreError("session_store_corrupt") from exc
            if updated != safety:
                self._write_unlocked(updated, claims)
            return decision

    def claim_and_reserve_safety(
        self,
        key: SignalKey,
        request: SafetyReservationRequest,
    ) -> SafetyReservationDecision:
        with self._locked():
            safety, claims = self._read_unlocked()
            existing = claims.get(key.digest())
            if existing is not None and existing.status in (
                ClaimStatus.UNCERTAIN,
                ClaimStatus.SUBMITTING,
            ):
                return SafetyReservationDecision(
                    False,
                    f"signal_key_{existing.status.value}",
                )
            current_claims = (
                record.status
                for record in claims.values()
                if not record.market_date
                or record.market_date == request.market_date
            )
            current_statuses = set(current_claims)
            if ClaimStatus.UNCERTAIN in current_statuses:
                return SafetyReservationDecision(
                    False,
                    "automatic_order_reconciliation_required",
                )
            if ClaimStatus.SUBMITTING in current_statuses:
                return SafetyReservationDecision(
                    False,
                    "automatic_order_submission_in_progress",
                )
            try:
                updated, decision = reserve_safety_state(safety, request)
            except SafetyReservationError as exc:
                raise SessionStoreError("session_store_corrupt") from exc
            if (
                existing is not None
                and decision.reason != "learned_daily_order_limit_reached"
            ):
                return SafetyReservationDecision(
                    False,
                    f"signal_key_{existing.status.value}",
                )
            if not decision.granted:
                if updated != safety:
                    self._write_unlocked(updated, claims)
                return decision
            if existing is not None:
                return SafetyReservationDecision(
                    False,
                    f"signal_key_{existing.status.value}",
                )
            claims[key.digest()] = ClaimRecord(ClaimStatus.SUBMITTING, key.market_date)
            self._write_unlocked(updated, claims)
            return decision

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
            claims[digest] = ClaimRecord(status, claims[digest].market_date)
            self._write_unlocked(safety, claims)

    def recover_interrupted_claims(self) -> int:
        with self._locked():
            safety, claims = self._read_unlocked()
            interrupted = tuple(
                digest
                for digest, record in claims.items()
                if record.status is ClaimStatus.SUBMITTING
            )
            for digest in interrupted:
                claims[digest] = ClaimRecord(
                    ClaimStatus.UNCERTAIN,
                    claims[digest].market_date,
                )
            if interrupted:
                self._write_unlocked(safety, claims)
            return len(interrupted)

    def save_safety_state(self, state: PersistedSafetyState) -> None:
        with self._locked():
            _, claims = self._read_unlocked()
            _ensure_valid_state(state)
            self._write_unlocked(state, claims)

    def merge_safety_state(
        self,
        state: PersistedSafetyState,
    ) -> None:
        with self._locked():
            persisted, claims = self._read_unlocked()
            _ensure_valid_state(state)
            try:
                merged = merge_persisted_safety_state(
                    persisted,
                    state,
                )
            except SessionStateCodecError as exc:
                raise SessionStoreError("session_store_corrupt") from exc
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

    def _read_unlocked(self) -> tuple[PersistedSafetyState, dict[str, ClaimRecord]]:
        if not self.path.exists():
            return PersistedSafetyState(), {}
        try:
            return read_session_payload(self.path)
        except (
            OSError,
            SessionPayloadError,
            SessionStateCodecError,
            ValueError,
        ) as exc:
            raise SessionStoreError("session_store_corrupt") from exc

    def _write_unlocked(
        self,
        safety: PersistedSafetyState,
        claims: dict[str, ClaimRecord],
    ) -> None:
        try:
            write_session_payload(self.path, safety, claims)
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
                state.position_high_water,
                state.closed_position_symbols,
                state.position_state_versions,
            )
        )
    except SessionStateCodecError as exc:
        raise SessionStoreError("session_store_corrupt") from exc
