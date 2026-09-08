from __future__ import annotations

from datetime import datetime

from .automatic_order_types import AutomaticOrderContext
from .live_authorization import LiveAuthorizationBlock, LiveAuthorizationEnvelope
from .live_authorization_store import LiveAuthorizationStore, LiveAuthorizationStoreError
from .market_hours import EASTERN, regular_market_session


class LiveAuthorizationRuntime:
    def __init__(
        self,
        store: LiveAuthorizationStore,
        *,
        broker_authorization_digest: str = "",
    ) -> None:
        self.store = store
        self.broker_authorization_digest = broker_authorization_digest
        self.envelope: LiveAuthorizationEnvelope | None = None
        self.block_reason = ""
        self.attempts = 0

    def set(
        self,
        authorization: LiveAuthorizationEnvelope | LiveAuthorizationBlock,
    ) -> None:
        if isinstance(authorization, LiveAuthorizationBlock):
            self.envelope = None
            self.block_reason = authorization.reason
            return
        self.envelope = authorization
        self.block_reason = ""
        self.attempts = 0

    def clear(self) -> str:
        try:
            self.store.clear()
        except LiveAuthorizationStoreError as exc:
            self.block_reason = exc.reason
            return exc.reason
        self.envelope = None
        self.block_reason = ""
        self.attempts = 0
        return ""

    def bind_broker(self, broker_authorization_digest: str) -> None:
        self.broker_authorization_digest = broker_authorization_digest

    def ensure_session(
        self,
        authorization: LiveAuthorizationEnvelope | LiveAuthorizationBlock,
    ) -> str:
        if isinstance(authorization, LiveAuthorizationBlock):
            return authorization.reason
        reason = self.reload()
        current = self.envelope
        if (
            current is not None
            and current.market_date == authorization.market_date
            and current.purpose == authorization.purpose
            and (
                current.max_attempts == 0
                or self.attempts < current.max_attempts
            )
        ):
            return reason
        if current is None and reason != "live_authorization_required":
            return reason
        try:
            stored = self.store.issue_automatic(authorization)
        except LiveAuthorizationStoreError as exc:
            self.envelope = None
            self.attempts = 0
            self.block_reason = exc.reason
            return exc.reason
        self.envelope = stored.envelope
        self.attempts = stored.attempts
        self.block_reason = ""
        return ""

    def reload(self) -> str:
        try:
            stored = self.store.load()
        except LiveAuthorizationStoreError as exc:
            self.envelope = None
            self.attempts = 0
            self.block_reason = exc.reason
            return exc.reason
        if stored is None:
            self.envelope = None
            self.attempts = 0
            self.block_reason = "live_authorization_required"
            return self.block_reason
        self.envelope = stored.envelope
        self.attempts = stored.attempts
        self.block_reason = ""
        if not self.broker_authorization_digest:
            self.block_reason = "live_authorization_broker_binding_required"
        elif (
            stored.envelope.broker_authorization_digest
            != self.broker_authorization_digest
        ):
            self.block_reason = "live_authorization_binding_changed"
        return self.block_reason

    def consume_attempt(
        self,
        context: AutomaticOrderContext,
        now: datetime,
    ) -> str:
        reason = self.reason(context, now)
        if reason:
            return reason
        envelope = self.envelope
        if envelope is None:
            return "live_authorization_required"
        try:
            reason, attempts = self.store.consume_attempt(envelope)
        except LiveAuthorizationStoreError as exc:
            reason, attempts = exc.reason, self.attempts
        self.attempts = attempts
        return reason

    def validate_current(
        self,
        context: AutomaticOrderContext,
        now: datetime,
    ) -> str:
        envelope = self.envelope
        if envelope is None:
            return "live_authorization_required"
        try:
            reason = self.store.validate_current(envelope)
        except LiveAuthorizationStoreError as exc:
            reason = exc.reason
        return reason or self.reason(context, now)

    def reason(
        self,
        context: AutomaticOrderContext,
        now: datetime,
    ) -> str:
        if now.tzinfo is None or now.utcoffset() is None:
            return "market_time_timezone_required"
        if self.block_reason:
            return self.block_reason
        envelope = self.envelope
        if envelope is None:
            return "live_authorization_required"
        session = regular_market_session(now)
        if not session.is_open:
            return "live_authorization_outside_regular_session"
        if now.astimezone(EASTERN).date() != envelope.market_date:
            return "live_authorization_market_date_mismatch"
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
            context.authorization_purpose == envelope.purpose,
            bool(self.broker_authorization_digest)
            and self.broker_authorization_digest
            == envelope.broker_authorization_digest,
        )
        return "" if all(bindings) else "live_authorization_binding_changed"
