from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class TradingModeValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ConfigLoadError(ValueError):
    path: Path
    reason: str

    def __str__(self) -> str:
        return f"invalid configuration: {self.path}: {self.reason}"
