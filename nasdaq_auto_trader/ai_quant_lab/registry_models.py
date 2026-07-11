from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique

from .strategy_schema import ResearchBasis
from .types import JsonObject


@unique
class StrategyStatus(StrEnum):
    RESEARCH_CANDIDATE = "research_candidate"
    SCHEMA_VALIDATED = "schema_validated"
    BACKTEST_PASSED = "backtest_passed"
    VALIDATION_PASSED = "validation_passed"
    PAPER_CANDIDATE = "paper_candidate"
    PAPER_TRADING = "paper_trading"
    SHADOW_LIVE = "shadow_live"
    CHAMPION = "champion"
    REJECTED = "rejected"
    RETIRED = "retired"
    ROLLBACK = "rollback"


@dataclass(frozen=True, slots=True)
class StrategyRecord:
    strategy_id: str
    version: str
    status: StrategyStatus
    allowed_for_live: bool
    manual_approval: bool
    research_basis: ResearchBasis
    score: float = 0.0
    rejection_reasons: tuple[str, ...] = ()

    def to_json_object(self) -> JsonObject:
        return {
            "strategy_id": self.strategy_id,
            "version": self.version,
            "status": self.status.value,
            "allowed_for_live": self.allowed_for_live,
            "manual_approval": self.manual_approval,
            "research_basis": {
                "provider": self.research_basis.provider,
                "research_ids": list(self.research_basis.research_ids),
                "source_ids": list(self.research_basis.source_ids),
                "summary": self.research_basis.summary,
            },
            "score": self.score,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    allowed: bool
    target_status: StrategyStatus
    reasons: tuple[str, ...]
