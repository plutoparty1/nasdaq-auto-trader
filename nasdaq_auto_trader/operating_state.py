from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum, unique
from pathlib import Path


@unique
class OperatingState(StrEnum):
    IDLE = "IDLE"
    MANUAL_TRAIN_ONLY = "MANUAL_TRAIN_ONLY"
    OFF_HOURS_LEARNING = "OFF_HOURS_LEARNING"
    PRE_MARKET_CHECK = "PRE_MARKET_CHECK"
    LIVE_TRADING = "LIVE_TRADING"
    POST_MARKET_RECONCILIATION = "POST_MARKET_RECONCILIATION"
    SAFE_HALT = "SAFE_HALT"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass(frozen=True, slots=True)
class StateTransitionError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class RuntimeState:
    state: OperatingState
    entered_at: datetime
    active_job_key: str | None = None
    champion_version: str | None = None
    daily_risk_used: float = 0.0

    @classmethod
    def idle(cls) -> RuntimeState:
        return cls(OperatingState.IDLE, datetime.now(timezone.utc))

    def to_json_object(self) -> dict[str, str | float | None]:
        return {
            "state": self.state.value,
            "entered_at": self.entered_at.astimezone(timezone.utc).isoformat(),
            "active_job_key": self.active_job_key,
            "champion_version": self.champion_version,
            "daily_risk_used": self.daily_risk_used,
        }


class OperatingStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState.idle()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return RuntimeState(
                state=OperatingState(payload["state"]),
                entered_at=datetime.fromisoformat(payload["entered_at"]).astimezone(timezone.utc),
                active_job_key=payload.get("active_job_key"),
                champion_version=payload.get("champion_version"),
                daily_risk_used=float(payload.get("daily_risk_used", 0.0)),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise StateTransitionError("runtime_state_corrupt") from exc

    def save(self, state: RuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state.to_json_object(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def claim_job(self, job_key: str, target: OperatingState) -> bool:
        current = self.load()
        if current.active_job_key == job_key:
            return False
        self.save(
            replace(
                current,
                state=target,
                entered_at=datetime.now(timezone.utc),
                active_job_key=job_key,
            )
        )
        return True

    def complete_job(self, safe_state: OperatingState = OperatingState.IDLE) -> None:
        current = self.load()
        self.save(
            replace(
                current,
                state=safe_state,
                entered_at=datetime.now(timezone.utc),
                active_job_key=None,
            )
        )
