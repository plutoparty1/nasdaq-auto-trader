from __future__ import annotations

from datetime import datetime
import time

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.models import OrderRequest
from nasdaq_auto_trader.automatic_order_audit import AutomaticOrderAuditor
from nasdaq_auto_trader.live_authorization import LiveAuthorizationBlock, LiveAuthorizationEnvelope
from nasdaq_auto_trader.live_authorization_store import LiveAuthorizationStore, LiveAuthorizationStoreError
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
    ) -> None:
        self.paths = paths
        self.session_store = session_store
        self.audit = audit
        self.order_auditor = AutomaticOrderAuditor(audit, session_store)
        self.authorization_store = authorization_store or LiveAuthorizationStore(
            session_store.path.with_suffix(".live-authorization.json")
        )
        self.live_authorization: LiveAuthorizationEnvelope | None = None
        self.authorization_block_reason = ""
        self.authorization_cycles = 0

    def set_live_authorization(
        self,
        authorization: LiveAuthorizationEnvelope | LiveAuthorizationBlock,
    ) -> None:
        if isinstance(authorization, LiveAuthorizationBlock):
            self.live_authorization = None
            self.authorization_block_reason = authorization.reason
            return
        try:
            stored = self.authorization_store.load_or_create(authorization)
        except LiveAuthorizationStoreError as exc:
            self.live_authorization = None
            self.authorization_block_reason = exc.reason
            self.authorization_cycles = 0
            return
        self.live_authorization = stored.envelope
        self.authorization_block_reason = ""
        self.authorization_cycles = stored.cycles

    def reset_live_authorization(self) -> str:
        try:
            self.authorization_store.clear()
        except LiveAuthorizationStoreError as exc:
            self.authorization_block_reason = exc.reason
            return exc.reason
        self.live_authorization = None
        self.authorization_block_reason = ""
        self.authorization_cycles = 0
        return ""

    def start_cycle(self, now: datetime) -> str:
        envelope = self.live_authorization
        if self.authorization_block_reason:
            return self.authorization_block_reason
        if envelope is None:
            return "live_authorization_required"
        try:
            reason, cycles = self.authorization_store.consume_cycle(envelope, now)
        except LiveAuthorizationStoreError as exc:
            return exc.reason
        self.authorization_cycles = cycles
        return reason

    def begin(
        self,
        context: AutomaticOrderContext,
        order: OrderRequest,
        now: datetime,
    ) -> AutomaticOrderDecision:
        started = time.monotonic()
        authorization_reason = self._authorization_reason(context, now)
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
        try:
            safety = self.session_store.reserve_safety(
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
                )
            )
        except SessionStoreError as exc:
            return self._blocked(
                AutomaticBlockRequest(context, order, exc.reason, started)
            )
        if not safety.granted:
            return self._blocked(
                AutomaticBlockRequest(context, order, safety.reason, started)
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
            claim = self.session_store.claim(key)
        except SessionStoreError as exc:
            return self._blocked(
                AutomaticBlockRequest(context, order, exc.reason, started)
            )
        if not claim.granted:
            return self._blocked(
                AutomaticBlockRequest(context, order, claim.reason, started)
            )
        return AutomaticOrderPermit(key, context, started)

    def confirm(
        self,
        permit: AutomaticOrderPermit,
        order: OrderRequest,
        now: datetime,
    ) -> AutomaticOrderBlock | None:
        reason = self._authorization_reason(permit.context, now)
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

    def _authorization_reason(
        self,
        context: AutomaticOrderContext,
        now: datetime,
    ) -> str:
        if self.authorization_block_reason:
            return self.authorization_block_reason
        envelope = self.live_authorization
        if envelope is None:
            return "live_authorization_required"
        if now >= envelope.expires_at:
            return "live_authorization_expired"
        if self.authorization_cycles < 1:
            return "live_authorization_cycle_required"
        if self.authorization_cycles > envelope.max_cycles:
            return "live_authorization_cycle_limit_reached"
        bindings = (
            context.strategy_id == envelope.strategy_id,
            context.strategy_version == envelope.strategy_version,
            context.strategy_digest == envelope.strategy_digest,
            context.universe_id == envelope.universe_id,
            context.universe_effective_date == envelope.universe_effective_date,
            context.universe_version == envelope.universe_version,
            context.risk_digest == envelope.risk_digest,
            context.mode == envelope.mode,
            context.learned_risk_digest == envelope.learned_risk_digest,
        )
        return "" if all(bindings) else "live_authorization_binding_changed"

    def finish(
        self,
        permit: AutomaticOrderPermit,
        response: JsonObject,
    ) -> AutomaticOrderBlock | None:
        return self.order_auditor.finish(permit, response)
