from __future__ import annotations

import json
from json import JSONDecodeError
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.file_lock import exclusive_file_lock

from .audit_logger import AuditEvent, NullAuditLogger
from .config import AIQuantConfig
from .registry_io import record_from_json
from .registry_models import PromotionDecision, StrategyRecord, StrategyStatus
from .registry_rollback import RollbackRequest, rollback_to_no_trade
from .scoring_engine import StrategyScore
from .strategy_schema import StrategySpec
from .types import JsonObject


class StrategyRegistry:
    def __init__(
        self,
        registry_path: str | Path,
        promoted_path: str | Path,
        config: AIQuantConfig | None = None,
        audit_logger: NullAuditLogger | None = None,
    ) -> None:
        self.registry_path = Path(registry_path)
        self.promoted_path = Path(promoted_path)
        self.config = config or AIQuantConfig()
        self.audit_logger = audit_logger or NullAuditLogger()

    def register_schema_validated(self, spec: StrategySpec) -> StrategyRecord:
        record = StrategyRecord(
            strategy_id=spec.strategy_id,
            version=spec.version,
            status=StrategyStatus.SCHEMA_VALIDATED,
            allowed_for_live=self.config.allowed_for_live_default,
            manual_approval=False,
            research_basis=spec.research_basis,
        )
        self._upsert(record)
        return record

    def evaluate_promotion(
        self,
        spec: StrategySpec,
        score: StrategyScore,
        requested_status: StrategyStatus = StrategyStatus.PAPER_CANDIDATE,
    ) -> PromotionDecision:
        reasons = _promotion_blockers(spec, score, requested_status)
        decision = PromotionDecision(
            allowed=not reasons,
            target_status=requested_status if not reasons else StrategyStatus.REJECTED,
            reasons=tuple(reasons),
        )
        record = StrategyRecord(
            strategy_id=spec.strategy_id,
            version=spec.version,
            status=decision.target_status,
            allowed_for_live=False,
            manual_approval=False,
            research_basis=spec.research_basis,
            score=score.final_score,
            rejection_reasons=decision.reasons,
        )
        audit_ok = self.audit_logger.append(
            AuditEvent(
                "promotion_evaluated",
                strategy_id=spec.strategy_id,
                strategy_version=spec.version,
                source_ids=spec.research_basis.source_ids,
                payload={"allowed": decision.allowed, "target_status": decision.target_status.value},
            )
        )
        if not audit_ok:
            decision = PromotionDecision(
                False,
                StrategyStatus.REJECTED,
                (*decision.reasons, "audit_log_write_failed"),
            )
            record = StrategyRecord(
                spec.strategy_id,
                spec.version,
                StrategyStatus.REJECTED,
                False,
                False,
                spec.research_basis,
                score.final_score,
                decision.reasons,
            )
        self._upsert(record)
        return decision

    def record_validation_passed(
        self,
        spec: StrategySpec,
        score: StrategyScore,
    ) -> StrategyRecord:
        record = StrategyRecord(
            strategy_id=spec.strategy_id,
            version=spec.version,
            status=StrategyStatus.VALIDATION_PASSED,
            allowed_for_live=False,
            manual_approval=False,
            research_basis=spec.research_basis,
            score=score.final_score,
            rejection_reasons=(),
        )
        self._upsert(record)
        return record

    def lock_champion(
        self,
        record: StrategyRecord,
        risk_limits_snapshot: JsonObject,
    ) -> PromotionDecision:
        reasons = _champion_lock_blockers(record, self.config)
        if reasons:
            return PromotionDecision(False, StrategyStatus.REJECTED, tuple(reasons))
        payload = {
            "active_strategy_id": record.strategy_id,
            "strategy_version": record.version,
            "status": StrategyStatus.CHAMPION.value,
            "mode": "live" if record.allowed_for_live else "paper",
            "allowed_for_live": record.allowed_for_live,
            "manual_approval": record.manual_approval,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "promotion_reason": "manual champion lock passed",
            "research_basis": {
                "provider": record.research_basis.provider,
                "research_ids": list(record.research_basis.research_ids),
                "source_ids": list(record.research_basis.source_ids),
            },
            "risk_limits_snapshot": risk_limits_snapshot,
        }
        audit_ok = self.audit_logger.append(
            AuditEvent(
                "strategy_promoted",
                strategy_id=record.strategy_id,
                strategy_version=record.version,
                source_ids=record.research_basis.source_ids,
            )
        )
        if not audit_ok:
            return PromotionDecision(
                False,
                StrategyStatus.REJECTED,
                ("audit_log_write_failed",),
            )
        self.promoted_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.promoted_path.with_suffix(self.promoted_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.promoted_path)
        return PromotionDecision(True, StrategyStatus.CHAMPION, ())

    def rollback_to_no_trade(self, reason: str) -> PromotionDecision:
        return rollback_to_no_trade(
            RollbackRequest(
                self.load_promoted_strategy(),
                self.promoted_path,
                self.audit_logger,
                self._upsert,
                reason,
            )
        )

    def load_records(self) -> tuple[StrategyRecord, ...]:
        if not self.registry_path.exists():
            return ()
        try:
            raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (JSONDecodeError, OSError):
            return ()
        if not isinstance(raw, list):
            return ()
        return tuple(
            record
            for item in raw
            if isinstance(item, dict)
            for record in [record_from_json(item)]
            if record is not None
        )

    def load_promoted_strategy(self) -> JsonObject | None:
        if not self.promoted_path.exists():
            return None
        try:
            raw = json.loads(self.promoted_path.read_text(encoding="utf-8"))
        except (JSONDecodeError, OSError):
            return None
        return raw if isinstance(raw, dict) else None

    def _upsert(self, record: StrategyRecord) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.registry_path.with_suffix(self.registry_path.suffix + ".lock")
        with exclusive_file_lock(lock_path, 2.0):
            records = [
                item
                for item in self.load_records()
                if (item.strategy_id, item.version)
                != (record.strategy_id, record.version)
            ]
            records.append(record)
            payload = [item.to_json_object() for item in records]
            temporary = self.registry_path.with_suffix(self.registry_path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(self.registry_path)


def _promotion_blockers(
    spec: StrategySpec,
    score: StrategyScore,
    requested_status: StrategyStatus,
) -> list[str]:
    reasons: list[str] = []
    if spec.research_basis.provider != "insane_search":
        reasons.append("research_provider_not_insane_search")
    if not spec.research_basis.source_ids:
        reasons.append("research_sources_missing")
    if score.rejection_reasons:
        reasons.extend(score.rejection_reasons)
    if (
        requested_status is not StrategyStatus.PAPER_CANDIDATE
        and not score.promotion_recommendation
    ):
        reasons.append("promotion_score_below_threshold")
    if requested_status in (StrategyStatus.CHAMPION, StrategyStatus.SHADOW_LIVE):
        reasons.append("paper_and_shadow_period_required")
    return reasons


def _champion_lock_blockers(
    record: StrategyRecord,
    config: AIQuantConfig,
) -> list[str]:
    reasons: list[str] = []
    if record.status != StrategyStatus.CHAMPION:
        reasons.append("record_not_champion")
    if record.research_basis.provider != "insane_search":
        reasons.append("research_provider_not_insane_search")
    if not record.research_basis.source_ids:
        reasons.append("research_sources_missing")
    if config.champion_requires_manual_approval and not record.manual_approval:
        reasons.append("manual_approval_required")
    if not record.allowed_for_live:
        reasons.append("allowed_for_live_false")
    return reasons
