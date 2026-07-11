import unittest

from nasdaq_auto_trader.quant_data.symbol_selector import (
    RankedSymbol,
    SelectionReport,
)
from nasdaq_auto_trader.selection_presenter import (
    selection_reason_label,
    selection_report_lines,
    selection_report_summary,
)


class AutoSymbolPresenterTests(unittest.TestCase):
    def test_selected_report_includes_identity_scores_and_reasons_in_korean(self):
        lines = selection_report_lines(_report("selected"))
        text = "\n".join(lines)

        self.assertIn("유니버스 기준일: 2026-07-10", text)
        self.assertIn("학습 전략: learned v1", text)
        self.assertIn("검토 종목 수: 1", text)
        self.assertIn("QQQ", text)
        self.assertIn("점수 1.5000", text)
        self.assertIn("이유: 상승 모멘텀", text)

    def test_no_trade_is_normal_and_missing_strategy_is_plain_korean(self):
        no_trade = _report("no_trade")
        blocked = SelectionReport(
            status="blocked",
            universe_id="nasdaq_100",
            universe_effective_date="2026-07-10",
            strategy_id="",
            strategy_version="",
            strategy_digest="",
            shortlist_count=0,
            ranked=(),
            selected_symbols=(),
            blocked_reasons=("eligible_strategy_unavailable",),
        )

        self.assertIn("이번 주기 매수 대상 없음", "\n".join(selection_report_lines(no_trade)))
        self.assertIn("학습 완료 전략 없음", "\n".join(selection_report_lines(blocked)))
        self.assertIn("자동 선택 차단", selection_report_summary(blocked))
        self.assertEqual(
            selection_reason_label("session_store_corrupt"),
            "거래 세션 기록이 손상되었습니다",
        )
        self.assertEqual(
            selection_reason_label("provider_timeout"),
            "확인 필요 (provider_timeout)",
        )


def _report(status: str) -> SelectionReport:
    selected = ("QQQ",) if status == "selected" else ()
    return SelectionReport(
        status=status,
        universe_id="nasdaq_100",
        universe_effective_date="2026-07-10",
        strategy_id="learned",
        strategy_version="v1",
        strategy_digest="digest",
        shortlist_count=1,
        ranked=(RankedSymbol("QQQ", 1.5, 0.8, ("momentum",)),),
        selected_symbols=selected,
    )


if __name__ == "__main__":
    unittest.main()
