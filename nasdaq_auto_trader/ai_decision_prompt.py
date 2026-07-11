from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .ai_market_summary import market_summary

if TYPE_CHECKING:
    from .ai_decision_manager import AIDecisionContext


def normalize_candidate_tickers(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        ticker = str(value).strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        result.append(ticker)
    return result


def build_ai_decision_prompt(
    context: AIDecisionContext,
    candidates: list[str] | None = None,
) -> str:
    settings = context.settings
    tickers = candidates or normalize_candidate_tickers(context.candidate_tickers)
    positions = {
        symbol: {
            "qty": position.qty,
            "market_value": position.market_value,
            "avg_entry_price": position.avg_entry_price,
        }
        for symbol, position in sorted(context.positions.items())
    }
    market_data = {
        ticker: market_summary(context.bars_by_symbol.get(ticker, []), settings)
        for ticker in tickers
    }
    return (
        "너는 나스닥 단기매매 보조 판단 엔진이다.\n\n"
        "아래 후보 종목 중에서만 판단해야 한다.\n"
        f"후보 종목: {json.dumps(tickers, ensure_ascii=False)}\n\n"
        "현재 계좌 상태:\n"
        f"- 사용 가능 현금: {context.account.buying_power}\n"
        f"- 현재 보유 종목 및 수량: {json.dumps(positions, ensure_ascii=False)}\n"
        f"- 최대 보유 수량: {settings.max_position_qty}\n"
        f"- AI 최대 주문 수량: {settings.ai_max_order_qty}\n"
        f"- 추가 매수 허용 여부: {settings.allow_additional_buy}\n"
        f"- 매도 전용 모드: {settings.sell_only}\n\n"
        f"시장 데이터: {json.dumps(market_data, ensure_ascii=False)}\n\n"
        "리스크 설정:\n"
        f"- 익절률: {settings.take_profit_rate}\n"
        f"- 손절률: {settings.stop_loss_rate}\n"
        f"- 트레일링 스탑 사용 여부: {settings.trailing_stop_enabled}\n"
        f"- 트레일링 스탑률: {settings.trailing_stop_rate}\n"
        f"- 일일 최대 손실률: {settings.max_daily_loss_rate}\n"
        f"- 장 마감 전 신규 매수 금지 시간: {settings.market_close_stop_minutes}\n\n"
        "반드시 아래 JSON 형식만 반환해라. 설명 문장, 마크다운, 코드블록은 절대 쓰지 마라.\n\n"
        "{\n"
        '  "action": "buy | sell | hold | skip",\n'
        '  "ticker": "후보 목록 중 하나",\n'
        '  "order_qty": 1,\n'
        '  "confidence": 0.0,\n'
        '  "reason": "판단 이유",\n'
        '  "risk": "위험 요소"\n'
        "}\n\n"
        "규칙:\n"
        "- 후보 목록 밖의 종목은 절대 선택하지 마라.\n"
        "- 확신이 낮으면 skip을 선택해라.\n"
        "- 주문 수량은 1 이상의 정수여야 한다.\n"
        "- 매수할 이유가 부족하면 hold 또는 skip을 선택해라.\n"
        "- 매도할 보유 수량이 없으면 sell을 선택하지 마라.\n"
    )
