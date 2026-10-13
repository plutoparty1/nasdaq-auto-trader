from __future__ import annotations

import time

from .ai_quant_lab.audit_logger import AuditEvent
from .ai_quant_lab.types import JsonObject
from .automatic_order_types import (
    AuditSink,
    AutomaticBlockRequest,
    AutomaticOrderBlock,
    AutomaticOrderPermit,
)
from .broker_response import (
    broker_response_reconcile_required,
    broker_response_submitted,
)
from .session_claims import AcceptedBuyReceipt, ClaimStatus
from .trading_session_store import SessionStoreError, TradingSessionStore


class AutomaticOrderAuditor:
    def __init__(self, audit: AuditSink, session_store: TradingSessionStore) -> None:
        self.audit = audit
        self.session_store = session_store

    def blocked(self, request: AutomaticBlockRequest) -> AutomaticOrderBlock:
        self.audit.append(
            AuditEvent(
                "automatic_order_blocked",
                strategy_id=request.context.strategy_id,
                strategy_version=request.context.strategy_version,
                payload={
                    "symbol": request.order.symbol,
                    "side": request.order.side,
                    "reason": request.reason,
                    "signal_timestamp": request.context.signal_timestamp,
                    "elapsed_milliseconds": round(
                        (time.monotonic() - request.started_monotonic) * 1000,
                        3,
                    ),
                },
            )
        )
        return AutomaticOrderBlock(request.reason, request.terminal)

    def finish(
        self,
        permit: AutomaticOrderPermit,
        response: JsonObject,
    ) -> AutomaticOrderBlock | None:
        submitted = broker_response_submitted(response)
        uncertain = broker_response_reconcile_required(response)
        status = (
            ClaimStatus.UNCERTAIN if uncertain
            else ClaimStatus.SUBMITTED if submitted else ClaimStatus.REJECTED
        )
        outcome_written = self.audit.append(
            AuditEvent(
                "automatic_order_submitted" if submitted else "automatic_order_blocked",
                strategy_id=permit.context.strategy_id,
                strategy_version=permit.context.strategy_version,
                payload={
                    "symbol": permit.key.symbol,
                    "side": permit.key.side,
                    "signal_timestamp": permit.key.signal_timestamp,
                    "broker_submitted": submitted,
                    "reason": (
                        "order_response_reconcile_required" if uncertain
                        else "" if submitted else "broker_response_not_submitted"
                    ),
                    "elapsed_milliseconds": round(
                        (time.monotonic() - permit.started_monotonic) * 1000,
                        3,
                    ),
                },
            )
        )
        if not outcome_written:
            return self._uncertain_outcome(permit)
        try:
            receipt = None
            if submitted and permit.key.side == "buy":
                output = response.get("output")
                order_id = output.get("ODNO") if isinstance(output, dict) else response.get("id")
                receipt = AcceptedBuyReceipt(
                    order_id if isinstance(order_id, str) else "",
                    permit.key.symbol, permit.key.market_date,
                    permit.initial_position_qty, permit.planned_quantity,
                )
            self.session_store.complete(permit.key, status, receipt)
        except SessionStoreError:
            return AutomaticOrderBlock(
                "claim_finalization_failed_reconcile_required",
                terminal=True,
            )
        if uncertain:
            return AutomaticOrderBlock("order_response_reconcile_required", terminal=True)
        return None

    def _uncertain_outcome(
        self,
        permit: AutomaticOrderPermit,
    ) -> AutomaticOrderBlock:
        try:
            self.session_store.complete(permit.key, ClaimStatus.UNCERTAIN)
        except SessionStoreError:
            return AutomaticOrderBlock(
                "order_outcome_and_claim_finalization_failed_reconcile_required",
                terminal=True,
            )
        return AutomaticOrderBlock(
            "order_outcome_audit_failed_reconcile_required",
            terminal=True,
        )
