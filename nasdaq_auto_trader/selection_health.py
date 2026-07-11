from __future__ import annotations

from dataclasses import dataclass

from .quant_data.symbol_selector import SelectionReport
from .selection_presenter import selection_reason_label


@dataclass(frozen=True, slots=True)
class AutomaticSelectionHealth:
    block_streak: int = 0
    persistent_error: str | None = None

    def observe(self, report: SelectionReport | None) -> AutomaticSelectionHealth:
        if report is None:
            return self
        if report.status == "selected":
            return AutomaticSelectionHealth()
        if report.status == "no_trade":
            return self
        block_streak = self.block_streak + 1
        persistent_error = self.persistent_error
        if block_streak >= 3:
            reasons = ", ".join(
                selection_reason_label(reason) for reason in report.blocked_reasons
            ) or selection_reason_label("unknown_selection_block")
            persistent_error = f"자동 종목 선택 3회 연속 차단: {reasons}"
        return AutomaticSelectionHealth(block_streak, persistent_error)
