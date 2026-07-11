from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

OperatorCommand = Literal[
    "status",
    "nightly",
    "champion-lock",
    "rollback",
    "monitor-degradation",
    "paper-shadow",
    "live-cycle",
]
TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class OperatorPaths:
    ai_config_path: Path | None
    registry_path: Path
    promoted_path: Path
    spec_dir: Path
    audit_log_path: Path


@dataclass(frozen=True, slots=True)
class UnsupportedCommandError(Exception):
    command: str

    def __str__(self) -> str:
        return f"unsupported ai-quant command: {self.command}"
