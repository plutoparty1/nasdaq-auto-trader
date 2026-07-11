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
    "insane_search_unavailable": "리서치 명령이 없어 연구 루프를 실행할 수 없음",
    "strategy_record_missing": "해당 전략 ID와 버전을 등록소에서 찾을 수 없음",
    "ai_quant_lab_disabled": "AI Quant Lab 기능이 설정에서 꺼져 있음",
}


def _text_value(value: JsonValue | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _human_reason(reason: str) -> str:
    return _REASON_LABELS.get(reason, reason)


def _reasons_text(value: JsonValue | None) -> str:
    if isinstance(value, list):
        parts = [_human_reason(item) for item in value if isinstance(item, str)]
        return ", ".join(parts)
    if isinstance(value, str):
        return _human_reason(value)
    return ""
