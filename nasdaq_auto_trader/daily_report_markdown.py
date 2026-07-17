from __future__ import annotations

from datetime import datetime

from .app_types import PortfolioSnapshot
from .daily_report_models import AuditSummary


def render_daily_report(
    market_date: str,
    generated_at: datetime,
    summary: AuditSummary,
    snapshot: PortfolioSnapshot | None,
) -> str:
    state_text = ", ".join(summary.states) if summary.states else "기록 없음"
    reason_text = " / ".join(summary.reasons) if summary.reasons else "없음"
    account_rows = _account_rows(snapshot)
    warning = (
        f"- 손상되거나 해석할 수 없는 감사 로그 {summary.skipped_lines}줄을 제외했습니다.\n"
        if summary.skipped_lines
        else ""
    )
    return (
        f"# NASDAQ Auto Trader 전일 운영 보고\n\n"
        f"- 미국 거래일: `{market_date}`\n"
        f"- 생성 시각: `{generated_at.astimezone().isoformat()}`\n\n"
        "## 운영 요약\n\n"
        "| 항목 | 결과 |\n|---|---:|\n"
        f"| 거래 판단 주기 | {summary.cycle_count} |\n"
        f"| 상태 전환 | {summary.transition_count} |\n"
        f"| 생성 후보 | {summary.generated_candidates} |\n"
        f"| 검증 통과 후보 | {summary.accepted_candidates} |\n"
        f"| 제출 주문 | {summary.submitted_orders} |\n"
        f"| 차단 주문 | {summary.blocked_orders} |\n\n"
        f"- 관찰 상태: {state_text}\n"
        f"- 차단 또는 점검 사유: {reason_text}\n"
        f"{warning}\n"
        "## 계좌 스냅샷\n\n"
        f"{account_rows}"
    )


def _account_rows(snapshot: PortfolioSnapshot | None) -> str:
    if snapshot is None:
        return "계좌 스냅샷을 확인할 수 없습니다.\n"
    account = snapshot.account
    return (
        "| 항목 | 금액 |\n|---|---:|\n"
        f"| 현금 | {account.cash:.2f} |\n"
        f"| 총자산 | {account.equity:.2f} |\n"
        f"| 주문 가능 금액 | {account.buying_power:.2f} |\n"
        f"| 보유 종목 수 | {len(snapshot.positions)} |\n"
    )
