from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .audit_logger import AuditEvent
from .registry_models import PromotionDecision, StrategyRecord, StrategyStatus
from .strategy_schema import ResearchBasis
from .types import JsonObject, JsonValue


class AuditAppender(Protocol):
    def append(self, event: AuditEvent) -> bool: ...


@dataclass(frozen=True, slots=True)
class RollbackRequest:
    promoted: JsonObject | None
    promoted_path: Path
    audit_logger: AuditAppender
    upsert: Callable[[StrategyRecord], None]
    reason: str


def rollback_to_no_trade(request: RollbackRequest) -> PromotionDecision:
    if request.promoted is None:
        return PromotionDecision(
            False,
            StrategyStatus.ROLLBACK,
            ("promoted_strategy_missing",),
        )
    reason = request.reason.strip() or "rollback_requested"
    basis = _research_basis(request.promoted)
    previous = _previous_strategy(request.promoted)
    audit_ok = request.audit_logger.append(
        AuditEvent(
            "rollback_triggered",
            severity="warning",
            strategy_id=_string(request.promoted.get("active_strategy_id")),
            strategy_version=_string(request.promoted.get("strategy_version")),
            source_ids=basis.source_ids,
            payload={"reason": reason, "previous_strategy": previous},
        )
    )
    reasons = (reason,) if audit_ok else (reason, "audit_log_write_failed")
    try:
        request.promoted_path.parent.mkdir(parents=True, exist_ok=True)
        request.promoted_path.write_text(
            json.dumps(_no_trade_payload(reason, basis, previous, audit_ok), indent=2),
            encoding="utf-8",
        )
        request.upsert(_rollback_record(request.promoted, basis, reasons))
    except OSError:
        return PromotionDecision(
            False,
            StrategyStatus.ROLLBACK,
            (*reasons, "rollback_write_failed"),
        )
    return PromotionDecision(True, StrategyStatus.ROLLBACK, reasons)


def _rollback_record(
    promoted: JsonObject,
    basis: ResearchBasis,
    reasons: tuple[str, ...],
) -> StrategyRecord:
    return StrategyRecord(
        strategy_id=_string(promoted.get("active_strategy_id")),
        version=_string(promoted.get("strategy_version")),
        status=StrategyStatus.ROLLBACK,
        allowed_for_live=False,
        manual_approval=False,
        research_basis=basis,
        rejection_reasons=reasons,
    )


def _no_trade_payload(
    reason: str,
    basis: ResearchBasis,
    previous: JsonObject,
    audit_ok: bool,
) -> JsonObject:
    payload: JsonObject = {
        "active_strategy_id": "",
        "strategy_version": "",
        "status": StrategyStatus.ROLLBACK.value,
        "mode": "no_trade",
        "allowed_for_live": False,
        "manual_approval": False,
        "rolled_back_at": datetime.now(timezone.utc).isoformat(),
        "rollback_reason": reason,
        "previous_strategy": previous,
        "research_basis": _basis_json(basis),
    }
    if not audit_ok:
        payload["rollback_warnings"] = ["audit_log_write_failed"]
    return payload


def _previous_strategy(promoted: JsonObject) -> JsonObject:
    return {
        "active_strategy_id": _string(promoted.get("active_strategy_id")),
        "strategy_version": _string(promoted.get("strategy_version")),
        "status": _string(promoted.get("status")),
        "mode": _string(promoted.get("mode")),
        "allowed_for_live": promoted.get("allowed_for_live") is True,
        "manual_approval": promoted.get("manual_approval") is True,
    }


def _research_basis(promoted: JsonObject) -> ResearchBasis:
    value = promoted.get("research_basis")
    payload = value if isinstance(value, dict) else {}
    return ResearchBasis(
        provider=_string(payload.get("provider")),
        research_ids=_string_tuple(payload.get("research_ids")),
        source_ids=_string_tuple(payload.get("source_ids")),
        summary=_string(payload.get("summary")),
    )


def _basis_json(basis: ResearchBasis) -> JsonObject:
    return {
        "provider": basis.provider,
        "research_ids": list(basis.research_ids),
        "source_ids": list(basis.source_ids),
        "summary": basis.summary,
    }


def _string(value: JsonValue | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_tuple(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
