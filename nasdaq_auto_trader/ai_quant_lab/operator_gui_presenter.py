from __future__ import annotations

from nasdaq_auto_trader.ai_quant_lab.operator_gui_models import (
    OperatorGuiActionCard,
    OperatorGuiBadgeLevel,
    OperatorGuiResult,
    OperatorGuiStatusView,
)
from nasdaq_auto_trader.ai_quant_lab.types import JsonValue


def operator_action_cards() -> tuple[OperatorGuiActionCard, ...]:
    return (
        OperatorGuiActionCard(
            "status",
            "1. 상태 확인",
            "설정, 전략 등록소, 라이브 주문 차단 상태를 한 번에 확인합니다.",
            "읽기 전용입니다. 파일이나 주문을 변경하지 않습니다.",
        ),
        OperatorGuiActionCard(
            "nightly",
            "2. 연구/전략 생성",
            "설정된 리서치 명령과 후보 JSON으로 전략 후보를 생성하고 검증합니다.",
            "운영 상태가 바뀔 수 있으므로 확인 창을 통과해야 실행됩니다.",
        ),
        OperatorGuiActionCard(
            "champion-lock",
            "3. 챔피언 잠금",
            "검증된 전략 ID와 버전을 배포 후보로 잠급니다.",
            "실거래 전 단계입니다. 누르기 전에 전략 ID와 버전을 확인해야 합니다.",
        ),
        OperatorGuiActionCard(
            "paper-shadow",
            "4. 페이퍼/섀도우 리허설",
            "가상 포지션 하나를 실행해 장부와 차단 사유를 확인합니다.",
            "실주문은 없지만 장부를 기록하므로 확인 창을 통과해야 실행됩니다.",
        ),
        OperatorGuiActionCard(
            "rollback",
            "5. 긴급 no-trade 롤백",
            "현재 승격 전략을 no-trade 상태로 되돌립니다.",
            "방어용 변경입니다. 확인 창을 통과해야 실행됩니다.",
        ),
        OperatorGuiActionCard(
            "live-guard",
            "6. 실거래 차단 점검",
            "실거래 가능 여부와 차단 사유를 읽기 전용으로 확인합니다.",
            "이 GUI는 실제 주문 실행 버튼을 제공하지 않습니다.",
        ),
    )


def gui_status_view(result: OperatorGuiResult) -> OperatorGuiStatusView:
    payload = result.payload
    config_valid = payload.get("config_valid") is True
    live_block_reason = _text_value(payload.get("live_block_reason"))
    promoted_status = _text_value(payload.get("promoted_status"))
    registry_records = payload.get("registry_records")

    if live_block_reason:
        badge_text = "실주문 차단"
        badge_level: OperatorGuiBadgeLevel = "safe"
        headline = "현재 GUI에서는 실제 주문이 나가지 않습니다."
        detail = f"차단 사유: {_human_reason(live_block_reason)}"
    elif config_valid:
        badge_text = "주의 필요"
        badge_level = "warning"
        headline = "설정상 라이브 차단 사유가 없습니다."
        detail = "GUI에는 실주문 버튼이 없지만, CLI/설정은 별도 검토가 필요합니다."
    else:
        badge_text = "설정 점검"
        badge_level = "blocked"
        headline = "설정 검증을 먼저 통과해야 합니다."
        detail = _reasons_text(payload.get("config_reasons")) or "설정 파일을 확인하세요."

    checklist = (
        f"설정 파일: {'정상' if config_valid else '점검 필요'}",
        f"라이브 가드: {_human_reason(live_block_reason) if live_block_reason else '차단 사유 없음'}",
        f"전략 등록소: {registry_records if isinstance(registry_records, int) else 0}개 기록",
        f"승격 전략: {promoted_status or '없음'}",
        "GUI 실주문 버튼: 없음",
    )
    return OperatorGuiStatusView(badge_text, badge_level, headline, detail, checklist)


def gui_result_explanation(result: OperatorGuiResult) -> tuple[str, ...]:
    payload = result.payload
    lines = [
        f"작업: {_COMMAND_LABELS.get(result.action, result.action)}",
        f"결과: {'완료' if result.exit_code == 0 else '차단 또는 점검 필요'}",
    ]
    status = _text_value(payload.get("status"))
    if status:
        lines.append(f"상태 코드: {status}")
    reasons = _reasons_text(payload.get("reasons") or payload.get("blocked_reasons"))
    if reasons:
        lines.append(f"사유: {reasons}")
    submitted_orders = payload.get("submitted_orders")
    if isinstance(submitted_orders, int):
        lines.append(f"제출된 실제 주문: {submitted_orders}건")
    fills = payload.get("fills")
    if isinstance(fills, int):
        lines.append(f"가상 체결: {fills}건")
    if result.summary:
        lines.append(f"원문 요약: {result.summary}")
    return tuple(lines)


_COMMAND_LABELS: dict[str, str] = {
    "status": "상태 확인",
    "nightly": "연구/전략 생성",
    "champion-lock": "챔피언 잠금",
    "rollback": "긴급 no-trade 롤백",
    "monitor-degradation": "성능 저하 감시",
    "paper-shadow": "페이퍼/섀도우 리허설",
    "live-cycle": "라이브 가드 점검",
}

_REASON_LABELS: dict[str, str] = {
    "live_trading_disabled": "실거래 기능이 설정에서 꺼져 있음",
    "dry_run_enabled": "드라이런이 켜져 있어 실주문을 차단함",
    "controlled_live_disabled": "통제된 실거래 단계가 꺼져 있음",
    "ai_quant_config_invalid": "인공지능 퀀트 설정 검증 실패",
    "insane_search_unavailable": "리서치 명령이 없어 연구 루프를 실행할 수 없음",
    "insane_search_command_unavailable": "리서치 명령 실행 파일을 찾을 수 없음",
    "insane_search_command_failed": "리서치 명령 실행 실패",
    "strategy_record_missing": "해당 전략 ID와 버전을 등록소에서 찾을 수 없음",
    "ai_quant_lab_disabled": "AI Quant Lab 기능이 설정에서 꺼져 있음",
    "self_improvement_disabled": "자가 개선 기능이 설정에서 꺼져 있음",
    "research_provider_must_be_insane_search": "리서치 제공자는 검증된 리서치 명령만 사용할 수 있음",
    "insane_search_command_must_be_string_list": "리서치 명령은 문자열 목록이어야 함",
    "insane_search_command_must_be_string_tuple": "리서치 명령은 문자열 목록이어야 함",
    "insane_search_timeout_seconds_must_be_int": "리서치 제한 시간은 정수여야 함",
    "insane_search_timeout_seconds_must_be_positive": "리서치 제한 시간은 1초 이상이어야 함",
    "allow_only_insane_search_for_research_must_be_true": "검증된 리서치 경로만 허용해야 함",
    "disable_research_if_insane_search_unavailable_must_be_true": "리서치 도구가 없으면 연구를 중단하도록 설정해야 함",
    "allow_ai_direct_order_must_be_false": "인공지능 직접 주문은 꺼져 있어야 함",
    "allow_dynamic_code_execution_must_be_false": "동적 코드 실행은 꺼져 있어야 함",
    "max_single_position_pct_out_of_range": "단일 종목 최대 비중 범위 초과",
    "max_total_exposure_pct_out_of_range": "전체 노출 최대 비중 범위 초과",
    "max_daily_loss_pct_out_of_range": "일일 손실 제한 범위 초과",
    "max_order_notional_must_be_positive": "주문 금액 한도는 0보다 커야 함",
    "max_orders_per_day_must_be_nonnegative": "하루 주문 횟수 한도는 0 이상이어야 함",
    "max_orders_per_day_must_be_int": "하루 주문 횟수 한도는 정수여야 함",
    "market_data_missing": "검증할 시장 데이터가 없음",
    "learning_already_running": "다른 학습 작업이 이미 실행 중임",
    "learning_cancelled": "사용자 요청으로 학습이 취소됨",
    "data_unchanged": "이전 학습과 동일한 완료 일봉 데이터임",
    "not_enough_bars": "학습에 필요한 일봉 데이터가 부족함",
    "market_data_timestamps_misaligned": "종목별 일봉 날짜가 서로 맞지 않음",
    "operating_model_unavailable": "검증 통과한 자동매매 전략이 없음",
    "market_data_unavailable": "시장 데이터 연결을 확인할 수 없음",
    "broker_unavailable": "증권사 연결을 확인할 수 없음",
    "account_state_unavailable": "계좌 상태를 확인할 수 없음",
    "order_response_reconcile_required": "주문 응답을 확인할 수 없어 계좌 대사가 필요함",
    "automatic_order_reconciliation_required": (
        "이전 주문 결과가 확정되지 않아 증권사 주문·체결 내역 대사가 필요함"
    ),
    "automatic_order_submission_in_progress": (
        "이전 자동주문을 제출 중이므로 중복 주문을 막기 위해 대기함"
    ),
    "operating_preflight_failed": "자동운영 사전 점검에 실패함",
    "runtime_state_corrupt": "자동운영 상태 파일을 읽을 수 없음",
    "market_data_timestamp_invalid": "시장 데이터 시간이 올바르지 않음",
    "market_data_timestamps_not_monotonic": "시장 데이터 시간이 순서대로 정렬되지 않음",
    "market_data_values_invalid": "시장 데이터 가격 또는 거래량 값이 올바르지 않음",
    "initial_cash_invalid": "초기 현금 값이 올바르지 않음",
    "backtest_failed": "백테스트 실패",
    "insufficient_oos_history": "표본 밖 검증 기간이 부족함",
    "independent_validation_required": "학습에 사용하지 않은 별도 기간의 검증이 필요함",
    "holdout_fixed_rule_unsupported": "현재 별도 기간 검증이 지원하지 않는 전략 규칙임",
    "holdout_cost_assumptions_invalid": "별도 기간 검증에 사용할 거래 비용 설정을 확인해야 함",
    "holdout_config_invalid": "별도 기간 검증 설정이 올바르지 않음",
    "holdout_history_insufficient": "학습 기간과 별도 검증 기간을 나눌 일봉 데이터가 부족함",
    "holdout_backtest_failed": "별도 기간 백테스트에 실패함",
    "holdout_evidence_invalid": "별도 기간 검증 결과가 올바르지 않음",
    "holdout_closed_trades_insufficient": "별도 검증 기간의 완료 거래가 3건 미만임",
    "holdout_return_not_positive": "별도 검증 기간의 비용 반영 수익률이 양수가 아님",
    "holdout_risk_adjusted_return_not_positive": "별도 검증 기간의 위험 조정 수익률이 양수가 아님",
    "holdout_profit_factor_unavailable": "별도 검증 기간의 손익비를 계산할 수 없음",
    "holdout_profit_factor_too_low": "별도 검증 기간의 손익비가 기준을 통과하지 못함",
    "holdout_drawdown_too_high": "별도 검증 기간의 최대 낙폭이 기준보다 큼",
    "holdout_turnover_too_high": "별도 검증 기간의 거래 회전율이 기준보다 높음",
    "max_drawdown_too_high": "최대 낙폭이 기준보다 큼",
    "turnover_too_high": "거래 회전율이 너무 높음",
    "advanced_overfit_evidence_insufficient": "과적합 검증 근거가 부족함",
    "purged_cross_validation_score_too_low": "누수 제거 교차검증 점수가 낮음",
    "cpcv_score_too_low": "조합형 교차검증 점수가 낮음",
    "pbo_probability_too_high": "과적합 확률이 높음",
    "deflated_sharpe_ratio_too_low": "보정 샤프 지수가 낮음",
    "profit_factor_missing": "손익비 지표가 없음",
    "overfit_metrics_missing": "과적합 점검 지표가 없음",
    "promotion_score_below_threshold": "승격 점수가 기준보다 낮음",
    "paper_and_shadow_period_required": "페이퍼와 섀도우 검증 기간이 필요함",
    "research_provider_not_insane_search": "전략 출처가 검증된 리서치 경로가 아님",
    "research_sources_missing": "전략 연구 출처가 없음",
    "manual_approval_required": "수동 승인이 필요함",
    "allowed_for_live_false": "실거래 허용 플래그가 꺼져 있음",
    "record_not_champion": "챔피언 전략 상태가 아님",
    "performance_samples_missing": "성과 표본이 없음",
    "strategy_drawdown_limit_exceeded": "전략 낙폭 한도 초과",
    "daily_loss_limit_exceeded": "일일 손실 한도 초과",
    "audit_log_write_failed": "감사 로그 기록 실패",
    "rollback_write_failed": "롤백 기록 저장 실패",
}


def _text_value(value: JsonValue | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def human_reason(reason: str) -> str:
    return _REASON_LABELS.get(reason, "한글 설명이 등록되지 않은 내부 점검 사유입니다.")


def _human_reason(reason: str) -> str:
    return human_reason(reason)


def _reasons_text(value: JsonValue | None) -> str:
    if isinstance(value, list):
        parts = [_human_reason(item) for item in value if isinstance(item, str)]
        return ", ".join(parts)
    if isinstance(value, str):
        return _human_reason(value)
    return ""
