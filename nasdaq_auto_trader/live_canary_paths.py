from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .quant_data.resources import application_data_root


@dataclass(frozen=True, slots=True)
class CanaryPaths:
    root: Path
    market_date: str

    @classmethod
    def for_market_date(cls, market_date: str) -> CanaryPaths:
        return cls(application_data_root() / "live_canary", market_date)

    @property
    def arm(self) -> Path:
        return self.root / f"live-canary-arm-{self.market_date}.json"

    @property
    def state(self) -> Path:
        return self.root / f"live-canary-state-{self.market_date}.json"

    @property
    def audit(self) -> Path:
        return self.root / "audit" / f"live-canary-{self.market_date}.jsonl"

    @property
    def process_lock(self) -> Path:
        return self.root / "live-canary.lock"

    @property
    def broker_lock(self) -> Path:
        return self.root / "broker-live-owner.lock"

    @property
    def exit_only_state(self) -> Path:
        return self.root / "exit-only-state.json"
