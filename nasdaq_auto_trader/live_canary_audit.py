from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Final, TypeAlias

from nasdaq_auto_trader.file_lock import FileLockTimeout, exclusive_file_lock


MAX_AUDIT_BYTES: Final = 10 * 1024 * 1024
RETENTION_DAYS: Final = 30
_FILE_PREFIX = "live-canary-"
_FILE_SUFFIX = ".jsonl"
_SECRET_KEY_PARTS = (
    "access_token",
    "api_key",
    "app_key",
    "app_secret",
    "authorization",
    "account_no",
    "account_number",
    "cookie",
    "password",
    "secret",
    "token",
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:kis_)?(?:access_token|api_key|app_key|app_secret|authorization|"
    r"account_no|account_number|cookie|password|secret|token)\b\s*[:=]\s*"
    r"(?:Bearer\s+)?[^,\s]+"
)
_BEARER_HEADER = re.compile(
    r"(?i)\bAuthorization\s*:\s*Bearer\s+[^\s,;]+"
)
_COOKIE_HEADER = re.compile(
    r"(?i)\b(?:Cookie|Set-Cookie)\s*:\s*[^\r\n,]+"
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class CanaryAuditError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class CanaryAuditEvent:
    market_date: str
    event_type: str
    fields: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _parse_market_date(self.market_date)
        if not self.event_type.strip():
            raise CanaryAuditError("audit event type is required")


class BoundedCanaryAuditLog:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path_for(self, market_date: str) -> Path:
        _parse_market_date(market_date)
        return self.directory / f"{_FILE_PREFIX}{market_date}{_FILE_SUFFIX}"

    def append(self, event: CanaryAuditEvent) -> bool:
        line = _encode(event)
        path = self.path_for(event.market_date)
        lock_path = self.directory / ".live-canary-audit.lock"
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with exclusive_file_lock(lock_path, 2.0):
                self._prune_unlocked(event.market_date)
                current_size = path.stat().st_size if path.exists() else 0
                if current_size + len(line) > MAX_AUDIT_BYTES:
                    return False
                with path.open("ab") as output:
                    output.write(line)
                    output.flush()
                    os.fsync(output.fileno())
        except (FileLockTimeout, OSError):
            return False
        return True

    def prune(self, current_market_date: str) -> None:
        _parse_market_date(current_market_date)
        lock_path = self.directory / ".live-canary-audit.lock"
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with exclusive_file_lock(lock_path, 2.0):
                self._prune_unlocked(current_market_date)
        except (FileLockTimeout, OSError):
            return

    def _prune_unlocked(self, current_market_date: str) -> None:
        cutoff = _parse_market_date(current_market_date) - timedelta(days=RETENTION_DAYS)
        for path in self.directory.glob(f"{_FILE_PREFIX}*{_FILE_SUFFIX}"):
            market_date = _date_from_path(path)
            if market_date is not None and market_date < cutoff:
                try:
                    path.unlink()
                except OSError:
                    continue


def _encode(event: CanaryAuditEvent) -> bytes:
    record: dict[str, JsonValue] = {
        "event_type": _redact_text(event.event_type),
        "fields": _redact_mapping(event.fields),
        "market_date": event.market_date,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    encoded = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (encoded + "\n").encode("utf-8")


def _redact_mapping(values: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in values.items():
        normalized = key.lower().replace("-", "_")
        if any(part in normalized for part in _SECRET_KEY_PARTS):
            result[key] = "[REDACTED]"
        else:
            result[key] = _redact_value(value)
    return result


def _redact_value(value: JsonValue) -> JsonValue:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return _redact_mapping(value)
    return value


def _redact_text(value: str) -> str:
    value = _BEARER_HEADER.sub("[REDACTED]", value)
    value = _COOKIE_HEADER.sub("[REDACTED]", value)
    return _SECRET_ASSIGNMENT.sub("[REDACTED]", value)


def _parse_market_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CanaryAuditError("market date must be ISO-8601 YYYY-MM-DD") from error


def _date_from_path(path: Path) -> date | None:
    value = path.name.removeprefix(_FILE_PREFIX).removesuffix(_FILE_SUFFIX)
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
