from __future__ import annotations

from datetime import datetime, timedelta

from .app_types import PortfolioSnapshot
from .learning_runner import LearningRunResult
from .runtime_journal import RuntimeEvent, RuntimeEventType, RuntimeJournalWriter


class ControllerRuntimeRecorder:
    def __init__(self, journal: RuntimeJournalWriter) -> None:
        self.journal = journal
        self._last_snapshot_at: datetime | None = None

    def transition(self, now: datetime, state: str, reason: str) -> None:
        self.journal.append(
            RuntimeEvent(
                RuntimeEventType.OPERATING_TRANSITION,
                now,
                state=state,
                reason=reason,
            )
        )

    def learning(
        self,
        now: datetime,
        result: LearningRunResult,
        completed_market_date: str,
    ) -> None:
        self.journal.append(
            RuntimeEvent(
                RuntimeEventType.LEARNING_COMPLETED,
                now,
                reason=result.reasons[0] if result.reasons else result.status,
                generated_candidates=result.generated_candidates,
                accepted_candidates=result.accepted_candidates,
                submitted_orders=result.submitted_orders,
                market_date=completed_market_date,
            )
        )

    def unattended_start(self, now: datetime, state: str) -> None:
        self.journal.append(
            RuntimeEvent(RuntimeEventType.UNATTENDED_STARTED, now, state=state)
        )

    def trading_cycle(self, now: datetime, state: str, result_count: int) -> None:
        self.journal.append(
            RuntimeEvent(
                RuntimeEventType.TRADING_CYCLE_COMPLETED,
                now,
                state=state,
                result_count=result_count,
            )
        )

    def portfolio(self, snapshot: PortfolioSnapshot) -> None:
        previous = self._last_snapshot_at
        if previous is not None and snapshot.as_of - previous < timedelta(minutes=15):
            return
        self.journal.append(
            RuntimeEvent(
                RuntimeEventType.PORTFOLIO_SNAPSHOT,
                snapshot.as_of,
                cash=snapshot.account.cash,
                equity=snapshot.account.equity,
                buying_power=snapshot.account.buying_power,
            )
        )
        self._last_snapshot_at = snapshot.as_of
