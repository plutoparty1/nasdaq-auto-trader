from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .ai_quant_lab.types import JsonObject
from .file_lock import FileLockTimeout, exclusive_file_lock
from .live_authorization import LiveAuthorizationEnvelope
from .live_authorization_codec import (
    LiveAuthorizationCodecError,
    StoredLiveAuthorization,
    parse_stored_authorization,
    stored_authorization_payload,
)


@dataclass(slots=True)  # noqa: MUTABLE_OK
class LiveAuthorizationStoreError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


class LiveAuthorizationStore:
    def __init__(self, path: Path, lock_timeout_seconds: float = 2.0) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self.revoked_path = path.with_suffix(path.suffix + ".revoked")
        self.lock_timeout_seconds = lock_timeout_seconds

    def issue(self, envelope: LiveAuthorizationEnvelope) -> StoredLiveAuthorization:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                self._archive_unlocked()
                stored = StoredLiveAuthorization(envelope)
                self._write_unlocked(stored)
                self.revoked_path.unlink(missing_ok=True)
                return stored
        except FileLockTimeout as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_lock_timeout"
            ) from exc
        except OSError as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_write_failed"
            ) from exc

    def issue_automatic(
        self,
        envelope: LiveAuthorizationEnvelope,
    ) -> StoredLiveAuthorization:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                if self.revoked_path.exists():
                    raise LiveAuthorizationStoreError("live_authorization_required")
                self._archive_unlocked()
                stored = StoredLiveAuthorization(envelope)
                self._write_unlocked(stored)
                return stored
        except FileLockTimeout as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_lock_timeout"
            ) from exc

    def load(self) -> StoredLiveAuthorization | None:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                if self.revoked_path.exists():
                    return None
                return self._read_unlocked()
        except FileLockTimeout as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_lock_timeout"
            ) from exc

    def consume_attempt(
        self,
        expected: LiveAuthorizationEnvelope,
    ) -> tuple[str, int]:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                if self.revoked_path.exists():
                    return "live_authorization_required", 0
                stored = self._read_unlocked()
                if stored is None:
                    return "live_authorization_required", 0
                if stored.envelope != expected:
                    return "live_authorization_binding_changed", stored.attempts
                if (
                    stored.envelope.max_attempts > 0
                    and stored.attempts >= stored.envelope.max_attempts
                ):
                    return (
                        "live_authorization_attempt_limit_reached",
                        stored.attempts,
                    )
                consumed = replace(stored, attempts=stored.attempts + 1)
                self._write_unlocked(consumed)
                return "", consumed.attempts
        except FileLockTimeout as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_lock_timeout"
            ) from exc

    def validate_current(self, expected: LiveAuthorizationEnvelope) -> str:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                if self.revoked_path.exists():
                    return "live_authorization_required"
                stored = self._read_unlocked()
                if stored is None:
                    return "live_authorization_required"
                return (
                    ""
                    if stored.envelope == expected
                    else "live_authorization_binding_changed"
                )
        except FileLockTimeout as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_lock_timeout"
            ) from exc

    def clear(self, *, archive: bool = False) -> bool:
        try:
            with exclusive_file_lock(self.lock_path, self.lock_timeout_seconds):
                self._write_revocation_unlocked()
                try:
                    if archive:
                        self._archive_unlocked()
                    else:
                        self.path.unlink(missing_ok=True)
                except (LiveAuthorizationStoreError, OSError):
                    return False
                return True
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
        try:
            return parse_stored_authorization(payload)
        except LiveAuthorizationCodecError as exc:
            raise LiveAuthorizationStoreError(exc.reason) from exc

    def _write_unlocked(self, stored: StoredLiveAuthorization) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as output:
                json.dump(
                    stored_authorization_payload(stored),
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

    def _write_revocation_unlocked(self) -> None:
        self.revoked_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.revoked_path.with_suffix(self.revoked_path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as output:
                output.write("revoked\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.revoked_path)
        except OSError as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_write_failed"
            ) from exc

    def _archive_unlocked(self) -> Path | None:
        if not self.path.exists():
            return None
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive = self.path.with_name(f"{self.path.name}.archive-{timestamp}")
        try:
            os.replace(self.path, archive)
        except OSError as exc:
            raise LiveAuthorizationStoreError(
                "live_authorization_store_write_failed"
            ) from exc
        return archive


__all__ = [
    "LiveAuthorizationStore",
    "LiveAuthorizationStoreError",
    "StoredLiveAuthorization",
]
