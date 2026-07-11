from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nasdaq_auto_trader.ai_quant_lab.operator_models import OperatorCommand
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject


@dataclass(frozen=True, slots=True)
class OperatorGuiResult:
    action: OperatorCommand
    payload: JsonObject
    exit_code: int
    summary: str


OperatorGuiBadgeLevel = Literal["safe", "warning", "blocked"]


@dataclass(frozen=True, slots=True)
class OperatorGuiStatusView:
    badge_text: str
    badge_level: OperatorGuiBadgeLevel
    headline: str
    detail: str
    checklist: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperatorGuiActionCard:
    key: str
    title: str
    description: str
    safety_note: str


@dataclass(frozen=True, slots=True)
class OperatorGuiInputError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason
