from __future__ import annotations

from pathlib import Path

from .day_trade_candidate import DayTradeCandidateMixin
from .day_trade_plan import DayTradePlanMixin
from .day_trade_store import OrderRecordStore
from .day_trade_submission import DayTradeSubmissionMixin
from .day_trade_types import DayTradeTestConfig


class DayTradeTestPlanner(
    DayTradePlanMixin,
    DayTradeCandidateMixin,
    DayTradeSubmissionMixin,
):
    def __init__(
        self,
        config: DayTradeTestConfig | None = None,
        record_store: OrderRecordStore | None = None,
    ) -> None:
        self.config = config or DayTradeTestConfig()
        self.record_store = record_store or OrderRecordStore(self.config.record_path)
