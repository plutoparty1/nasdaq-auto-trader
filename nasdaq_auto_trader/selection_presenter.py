from __future__ import annotations

from typing import assert_never

from .quant_data.symbol_selector import SelectionReport


REASON_LABELS = {
    "eligible_strategy_unavailable": "학습 완료 전략 없음",
    "promoted_strategy_missing": "승격된 학습 전략이 없습니다",
    "promoted_strategy_not_champion": "승격 전략이 챔피언 상태가 아닙니다",
    "manual_approval_missing": "승격 전략의 수동 승인이 없습니다",
    "promoted_strategy_not_allowed_for_live": "승격 전략의 실거래 권한이 없습니다",
    "strategy_spec_missing_or_invalid": "학습 전략 명세가 없거나 올바르지 않습니다",
    "market_data_incomplete": "시세 데이터가 부족합니다",
    "promoted_strategy_rollback": "승격 전략이 no-trade로 롤백되었습니다",
    "universe_snapshot_stale": "종목 목록 기준일이 만료되었습니다",
    "audit_log_write_failed": "감사 기록 저장에 실패했습니다",
    "session_store_corrupt": "거래 세션 기록이 손상되었습니다",
    "session_store_lock_timeout": "거래 세션 기록을 잠그지 못했습니다",
    "session_store_write_failed": "거래 세션 기록을 저장하지 못했습니다",
    "promoted_strategy_id_changed": "선택 후 승격 전략 ID가 변경되었습니다",
    "promoted_strategy_version_changed": "선택 후 승격 전략 버전이 변경되었습니다",
    "promoted_strategy_digest_changed": "선택 후 승격 전략 내용이 변경되었습니다",
    "momentum": "상승 모멘텀",
    "liquidity": "거래 유동성",
}

REASON_GUIDANCE = {
    "eligible_strategy_unavailable": (
        "실주문은 하지 말고 자동 선택을 끈 뒤 연습 모드에서만 수동 종목을 입력하거나, "
        "인공지능 퀀트 연구실에서 새 후보를 백테스트해 모의 후보 상태로 통과시키세요. "
        "탈락 전략 기록을 직접 수정하면 안 됩니다."
    ),
}

SIGNAL_LABELS = {
    "trend_following": "추세 추종",
    "cross_sectional_momentum": "종목 간 모멘텀",
    "time_series_momentum": "시계열 모멘텀",
    "mean_reversion": "평균 회귀",
    "bollinger_zscore": "볼린저 편차",
    "rsi_oscillator": "RSI 과매수·과매도",
    "volatility_breakout": "변동성 돌파",
    "breakout": "가격 돌파",
    "pair_trading_stat_arb": "페어 통계 차익",
    "factor_strategy": "팩터 전략",
    "sector_theme_rotation": "섹터 순환",
    "volatility_targeting": "변동성 목표",
    "volatility_filter": "변동성 필터",
}


def selection_report_lines(report: SelectionReport) -> list[str]:
    strategy = (
        f"학습 전략: {report.strategy_id} {report.strategy_version}"
        if report.strategy_id
        else "학습 완료 전략 없음"
    )
    lines = [
        f"유니버스 기준일: {report.universe_effective_date}",
        strategy,
        f"검토 종목 수: {report.shortlist_count}",
    ]
    match report.status:
        case "selected":
            lines.append("자동 선택 종목: " + ", ".join(report.selected_symbols))
            lines.extend(_ranked_lines(report))
        case "no_trade":
            lines.append("이번 주기 매수 대상 없음 (정상 no-trade)")
        case "blocked":
            reasons = report.blocked_reasons or ("unknown_selection_block",)
            for reason in reasons:
                lines.append(f"차단 사유: {selection_reason_label(reason)}")
                guidance = REASON_GUIDANCE.get(reason)
                if guidance:
                    lines.append(f"해결 방법: {guidance}")
        case unexpected:
            assert_never(unexpected)
    lines.extend(
        f"주의: {selection_reason_label(warning)}" for warning in report.warnings
    )
    return lines


def selection_report_summary(report: SelectionReport) -> str:
    match report.status:
        case "selected":
            symbols = ", ".join(report.selected_symbols)
            return (
                f"자동 선택 완료 | {symbols} | {report.strategy_id} "
                f"{report.strategy_version} | 기준일 {report.universe_effective_date}"
            )
        case "no_trade":
            return (
                "자동 선택 정상 | 이번 주기 매수 대상 없음 | "
                f"기준일 {report.universe_effective_date}"
            )
        case "blocked":
            reason = (
                report.blocked_reasons[0]
                if report.blocked_reasons
                else "unknown_selection_block"
            )
            return f"자동 선택 차단 | {selection_reason_label(reason)}"
        case unexpected:
            assert_never(unexpected)


def _ranked_lines(report: SelectionReport) -> list[str]:
    lines: list[str] = []
    for item in report.ranked:
        reasons = ", ".join(
            selection_reason_label(reason) for reason in item.reasons
        ) or "-"
        lines.append(
            f"{item.symbol}: 점수 {item.score:.4f}, 신뢰도 {item.confidence:.1%}"
        )
        lines.append(f"{item.symbol} 선택 이유: {reasons}")
    return lines


def selection_reason_label(reason: str) -> str:
    if reason in REASON_LABELS:
        return REASON_LABELS[reason]
    signal, separator, value = reason.partition(":")
    if separator and signal in SIGNAL_LABELS:
        return f"{SIGNAL_LABELS[signal]} ({value})"
    return f"확인 필요 ({reason})"
