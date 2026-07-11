from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from nasdaq_auto_trader.file_lock import FileLockTimeout, exclusive_file_lock

from .types import JsonObject


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_type: str
    severity: str = "info"
    payload: JsonObject = field(default_factory=dict)
    experiment_id: str | None = None
    research_id: str | None = None
    source_ids: tuple[str, ...] = ()
    strategy_id: str | None = None
    strategy_version: str | None = None
    error: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_json_object(self) -> JsonObject:
        data: JsonObject = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "severity": self.severity,
            "payload": self.payload,
            "source_ids": list(self.source_ids),
        }
        optional = {
            "experiment_id": self.experiment_id,
            "research_id": self.research_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "error": self.error,
        }
        for key, value in optional.items():
            if value is not None:
                data[key] = value
        return data


class AuditLogger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.last_error: str | None = None
        self.durable = True
        self.lock_timeout_seconds = 2.0

    def append(self, event: AuditEvent) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock_path = self.path.with_suffix(self.path.suffix + ".lock")
            with exclusive_file_lock(lock_path, self.lock_timeout_seconds):
                with self.path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(event.to_json_object(), sort_keys=True) + "\n")
                    file.flush()
                    os.fsync(file.fileno())
        except (FileLockTimeout, OSError) as error:
            self.last_error = str(error)
            return False
        self.last_error = None
        return True


class NullAuditLogger:
    def __init__(self, durable: bool = False) -> None:
        self.events: list[AuditEvent] = []
        self.fail_writes = False
        self.durable = False

    def append(self, event: AuditEvent) -> bool:
        if self.fail_writes:
            return False
        self.events.append(event)
        return True
