from __future__ import annotations

from .app_types import EngineResult


def _summarize_trade_result(item: EngineResult) -> str:
    ai_decision = item.get("ai_decision")
    if isinstance(ai_decision, dict):
        recommendation = ai_decision.get("recommendation") or {}
        if isinstance(recommendation, dict):
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
        return (
            "[AI 추천] "
            f"실패: {ai_decision.get('error', '-')} / "
            f"최종 상태: {ai_decision.get('final_status', '-')}"
        )

    symbol = str(item.get("symbol", "-"))
    decision = item.get("decision")
    action = getattr(decision, "action", None) or "-"
    score = getattr(decision, "score", None)
    price = getattr(decision, "latest_price", None)
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

    return (
        f"{symbol}: action={action}, score={score}, price={_format_optional_currency(price)}, "
        f"{order_text}, response={response_text}"
    )


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
