from __future__ import annotations

from .app_types import EngineResult
from .exit_diagnostics import ExitDiagnostics

AI_FAILURE_MESSAGES = {
    "ai_provider_unavailable": (
        "외부 AI 추천 기능이 준비되지 않았습니다. 학습·검증 데이터로 종목을 자동 선택하려면 "
        "먼저 적격 학습 전략을 준비한 뒤 설정에서 '과거 데이터 기반 종목 자동 선택'을 켜세요."
    ),
    "ai_decision_interval_active": (
        "설정한 AI 판단 간격이 아직 지나지 않아 이번 실행을 건너뜁니다."
    ),
}


def _summarize_trade_result(item: EngineResult) -> str:
    ai_decision = item.get("ai_decision")
    if isinstance(ai_decision, dict):
        recommendation = ai_decision.get("recommendation")
        if isinstance(recommendation, dict) and recommendation:
            response = item.get("response")
            final_status = ai_decision.get("final_status")
            if isinstance(response, dict) and response.get("status") == "blocked":
                final_status = f"주문 차단: {response.get('reason')}"
            return (
                "[AI 추천] "
                f"액션: {str(recommendation.get('action', '-')).upper()} / "
                f"종목: {recommendation.get('ticker', '-')} / "
                f"수량: {recommendation.get('order_qty', '-')} / "
                f"신뢰도: {recommendation.get('confidence', '-')} / "
                f"이유: {recommendation.get('reason', '-')} / "
                f"리스크: {recommendation.get('risk', '-')} / "
                f"최종 상태: {final_status or '-'}"
            )
        return _summarize_ai_failure(item, ai_decision)

    symbol = str(item.get("symbol", "-"))
    decision = item.get("decision")
    action = getattr(decision, "action", None) or "-"
    score = getattr(decision, "score", None)
    price = getattr(decision, "latest_price", None)
    reasons = ",".join(getattr(decision, "reasons", ())) or "-"
    order = item.get("order")
    response = item.get("response")

    order_text = "주문 없음"
    if order is not None:
        side = getattr(order, "side", "-")
        qty = getattr(order, "qty", None)
        notional = getattr(order, "notional", None)
        order_text = f"{side} qty={qty} notional={notional}"

    response_text = "-"
    if isinstance(response, dict):
        response_text = str(response.get("status") or response.get("rt_cd") or response)
        if response.get("status") == "blocked":
            response_text = f"blocked:{response.get('reason')}"
    elif response is not None:
        response_text = str(response)

    diagnostics = item.get("exit_diagnostics")
    context = ""
    if isinstance(diagnostics, ExitDiagnostics):
        context = (
            f", exit_context={diagnostics.to_json()}, "
            f"evaluated_at={item.get('evaluation_timestamp')}, "
            f"indicator_timeframe={item.get('indicator_timeframe')}"
        )
    return (
        f"{symbol}: action={action}, score={score}, price={_format_optional_currency(price)}, "
        f"{order_text}, response={response_text}, reasons={reasons}{context}"
    )


def _summarize_ai_failure(
    item: EngineResult,
    ai_decision: EngineResult,
) -> str:
    response = item.get("response")
    reason = ai_decision.get("error_code")
    final_status = ai_decision.get("final_status") or "실패"
    if isinstance(response, dict) and response.get("status") == "blocked":
        reason = response.get("reason") or reason
        final_status = "주문 차단"
    message = AI_FAILURE_MESSAGES.get(
        str(reason),
        "AI 추천을 만들거나 읽지 못해 이번 실행을 안전하게 건너뜁니다.",
    )
    return f"[AI 추천] {message} / 최종 상태: {final_status}"


def _mode_label(mode: str) -> str:
    return {
        "live": "실거래",
        "dry_run": "드라이런",
    }.get(mode, "모의거래")


def _format_currency(value: float) -> str:
    return f"{value:,.4f}"


def _format_optional_currency(value: float | None) -> str:
    return "-" if value is None else _format_currency(value)


def _format_optional_pct(value: float | None) -> str:
    return "-" if value is None else f"{value:,.2f}%"


def _format_number(value: float, digits: int = 4) -> str:
    text = f"{value:,.{digits}f}"
    return text.rstrip("0").rstrip(".")
