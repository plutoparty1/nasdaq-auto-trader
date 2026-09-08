from __future__ import annotations

from datetime import datetime
import time

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.models import OrderRequest
from nasdaq_auto_trader.automatic_order_audit import AutomaticOrderAuditor
from nasdaq_auto_trader.live_authorization import LiveAuthorizationBlock, LiveAuthorizationEnvelope
from nasdaq_auto_trader.live_authorization_runtime import LiveAuthorizationRuntime
from nasdaq_auto_trader.live_authorization_store import LiveAuthorizationStore
from nasdaq_auto_trader.market_hours import EASTERN
from nasdaq_auto_trader.session_claims import ClaimStatus, SignalKey
from nasdaq_auto_trader.automatic_order_readiness import live_readiness_reason
from nasdaq_auto_trader.automatic_order_types import (
    AuditSink,
    AutomaticBlockRequest,
    AutomaticOrderBlock,
    AutomaticOrderContext,
    AutomaticOrderDecision,
    AutomaticOrderPermit,
)
from nasdaq_auto_trader.trading_session_store import (
    SafetyReservationRequest,
    SessionStoreError,
    TradingSessionStore,
)


class AutomaticOrderGuard:
    def __init__(
        self,
        paths: StrategyArtifactPaths,
        session_store: TradingSessionStore,
        audit: AuditSink,
        authorization_store: LiveAuthorizationStore | None = None,
        *,
        broker_authorization_digest: str = "",
    ) -> None:
        self.paths = paths
        self.session_store = session_store
        self.audit = audit
        self.order_auditor = AutomaticOrderAuditor(audit, session_store)
        self._authorization = LiveAuthorizationRuntime(
            authorization_store
            or LiveAuthorizationStore(
                session_store.path.with_suffix(".live-authorization.json")
            ),
            broker_authorization_digest=broker_authorization_digest,
        )

    @property
    def authorization_store(self) -> LiveAuthorizationStore:
        return self._authorization.store

    @property
    def live_authorization(self) -> LiveAuthorizationEnvelope | None:
        return self._authorization.envelope

    @property
    def authorization_block_reason(self) -> str:
        return self._authorization.block_reason

    @property
    def authorization_attempts(self) -> int:
        return self._authorization.attempts

    def set_live_authorization(
        self,
        authorization: LiveAuthorizationEnvelope | LiveAuthorizationBlock,
    ) -> None:
        self._authorization.set(authorization)

    def reset_live_authorization(self) -> str:
        return self._authorization.clear()

    def bind_broker_authorization(self, broker_authorization_digest: str) -> None:
        self._authorization.bind_broker(broker_authorization_digest)

    def ensure_live_authorization(
        self,
        authorization: LiveAuthorizationEnvelope | LiveAuthorizationBlock,
    ) -> str:
        return self._authorization.ensure_session(authorization)

    def start_cycle(self, now: datetime) -> str:
        del now
        return self._authorization.reload()

    def begin(
        self,
        context: AutomaticOrderContext,
        order: OrderRequest,
        now: datetime,
    ) -> AutomaticOrderDecision:
        started = time.monotonic()
        authorization_reason = self._authorization.consume_attempt(context, now)
        if authorization_reason:
            return self._blocked(
                AutomaticBlockRequest(
                    context,
                    order,
                    authorization_reason,
                    started,
                    True,
                )
            )
        if not context.signal_timestamp:
            return self._blocked(
                AutomaticBlockRequest(
                    context,
                    order,
                    "automatic_signal_timestamp_missing",
                    started,
                )
            )
        readiness_reason = live_readiness_reason(context, self.paths, now)
        if readiness_reason:
            return self._blocked(
                AutomaticBlockRequest(
                    context,
                    order,
                    readiness_reason,
                    started,
                    True,
                )
            )
        intent = AuditEvent(
            "automatic_order_intent",
            strategy_id=context.strategy_id,
            strategy_version=context.strategy_version,
            payload={
                "symbol": order.symbol,
                "side": order.side,
                "signal_timestamp": context.signal_timestamp,
                "universe_effective_date": context.universe_effective_date,
            },
        )
        if not self.audit.append(intent):
            return AutomaticOrderBlock("audit_log_write_failed")
        key = SignalKey(
            market_date=now.astimezone(EASTERN).date().isoformat(),
            strategy_id=context.strategy_id,
            strategy_version=context.strategy_version,
            symbol=order.symbol,
            side=order.side,
            signal_timestamp=context.signal_timestamp,
        )
        try:
            reservation = self.session_store.claim_and_reserve_safety(
                key,
                SafetyReservationRequest(
                    market_date=now.astimezone(EASTERN).date().isoformat(),
                    side=order.side,
                    timestamp=now.isoformat(),
                    max_daily_buy_count=context.max_daily_buy_count,
                    max_daily_sell_count=context.max_daily_sell_count,
                    cooldown_minutes=context.cooldown_minutes,
                    daily_loss_breached=context.daily_loss_breached,
                    daily_loss_state_unavailable=(
                        context.daily_loss_state_unavailable
                    ),
                    baseline_available=context.baseline_available,
                    max_daily_order_count=context.max_daily_order_count,
                ),
            )
        except SessionStoreError as exc:
            return self._blocked(
                AutomaticBlockRequest(context, order, exc.reason, started)
            )
        if not reservation.granted:
            return self._blocked(
                AutomaticBlockRequest(
                    context,
                    order,
                    reservation.reason,
                    started,
                    reservation.reason
                    == "automatic_order_reconciliation_required",
                )
            )
        return AutomaticOrderPermit(key, context, started)

    def confirm(
        self,
        permit: AutomaticOrderPermit,
        order: OrderRequest,
        now: datetime,
    ) -> AutomaticOrderBlock | None:
        reason = self._authorization.validate_current(permit.context, now)
        if not reason:
            reason = live_readiness_reason(permit.context, self.paths, now)
        if not reason:
            return None
        try:
            self.session_store.complete(permit.key, ClaimStatus.REJECTED)
        except SessionStoreError:
            return AutomaticOrderBlock(
                "automatic_order_reconciliation_required",
                True,
            )
        return self._blocked(
            AutomaticBlockRequest(
                permit.context,
                order,
                reason,
                permit.started_monotonic,
                True,
            )
        )

    def record_block(
        self,
        request: AutomaticBlockRequest,
    ) -> None:
        self.order_auditor.blocked(request)

    def _blocked(
        self,
        request: AutomaticBlockRequest,
    ) -> AutomaticOrderBlock:
        return self.order_auditor.blocked(request)

    def finish(
        self,
        permit: AutomaticOrderPermit,
        response: JsonObject,
    ) -> AutomaticOrderBlock | None:
        return self.order_auditor.finish(permit, response)
