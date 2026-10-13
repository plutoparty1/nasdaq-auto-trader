from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from .ai_quant_lab.types import JsonObject, JsonValue
from .app_controller import AutoTradeController
from .production_fees import FeeScheduleInput


class ProductionFacade(Protocol):
    @property
    def controller(self) -> AutoTradeController: ...

    def preflight(self) -> JsonObject: ...
    def prepare_start(self) -> JsonObject: ...
    def confirm_start(self, confirmation: str, review_digest: str) -> JsonObject: ...
    def review(self) -> JsonObject: ...
    def status(self) -> JsonObject: ...
    def configure_fees(self, confirmed: bool) -> JsonObject: ...
    def configure_fee_profile(self, profile: FeeScheduleInput) -> JsonObject: ...
    def authorize(self, confirmation: str, review_digest: str) -> JsonObject: ...
    def start_live(self) -> JsonObject: ...
    def start_simulation(self) -> JsonObject: ...
    def stop_entries(self) -> JsonObject: ...
    def shutdown(self) -> JsonObject: ...


def approve_review(
    service: ProductionFacade, *, confirmation: str, digest: str,
    fees_confirmed: bool,
) -> JsonObject:
    """Require the displayed review and an explicit fee acknowledgement."""
    if not fees_confirmed or not confirmation.strip() or not digest:
        return {"status": "blocked", "blockers": ["explicit_review_confirmation_required"]}
    return service.authorize(confirmation, digest)


def confirm_prepared_start(service: ProductionFacade, *, confirmation: str, review: JsonObject) -> JsonObject:
    digest = review.get("review_digest")
    if (review.get("blockers") or review.get("status") != "ready_for_explicit_approval"
            or not confirmation.strip() or not isinstance(digest, str) or not digest):
        return {"status": "blocked", "blockers": review.get("blockers") or ["prepared_review_required"]}
    return service.confirm_start(confirmation, digest)


def review_summary(review: JsonObject) -> str:
    rows = ["최종 운용 조건 · 아직 승인되지 않았습니다."]
    labels = {"account_masked": "적용 계좌", "strategy_id": "운영 전략", "strategy_version": "전략 버전",
              "build_id": "실행본 식별", "executable_sha256": "실행본 SHA256", "checked_at": "조회 시각", "account": "적용 계좌", "before_after": "변경 전 → 적용 초안",
              "automatic_plan": "자동 계산 한도 ($)", "approval_window": "승인 기간과 만료 동작",
              "fee_instructions": "실제 수수료 확인 항목", "blockers": "남은 차단 사유"}
    for key, label in labels.items():
        value = review.get(key)
        if value is None:
            continue
        rows.append(label)
        match value:
            case dict():
                rows.extend(_condition_lines(value, "  "))
            case list():
                rows.extend(f"  {display_value(key, item)}" for item in value)
            case _:
                rows.append(f"  {value}")
    if not review.get("approval_window"):
        rows.append("승인 기간 미확인 · 실거래 시작 차단")
    return "\n".join(rows)


def display_field(name: str) -> str:
    labels = {"duration_hours": "승인 유효 시간", "expires_at": "만료 시각",
              "expiry_behavior": "만료 후 동작", "cash_usd": "현금",
              "symbol_limit_usd": "종목 투입 상한", "total_limit_usd": "전체 투입 상한",
              "risk_budget_usd": "거래 위험 예산", "quantity": "주문 수량",
              "masked_account": "계좌", "equity": "계좌 평가액", "cash": "현금",
              "before": "변경 전", "after": "적용 초안"}
    return labels.get(name, name)


def display_value(name: str, value: JsonValue) -> str:
    if name == "expires_at" and isinstance(value, str):
        try:
            expires = datetime.fromisoformat(value)
        except ValueError:
            return value
        if expires.tzinfo is not None:
            return expires.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
    if name.endswith("_usd") and isinstance(value, int | float) and not isinstance(value, bool):
        return f"${value:,.4f}"
    reasons = {"actual_fee_review_required": "실제 계좌 수수료 자료 확인 필요",
               "actual_fees_unconfirmed": "실제 수수료 미확인", "preflight_required": "사전점검 필요",
               "strategy_live_not_approved": "전략의 정식 실전 검증 미충족",
               "other_trader_process_present": "다른 운영 프로그램 실행 중",
               "account_funding_required": "계좌 현금·평가액 조건 미충족"}
    if name == "blockers" and isinstance(value, str):
        return reasons.get(value, value)
    return str(value)


def approval_window_text(review: JsonObject) -> str:
    window = review.get("approval_window")
    if not isinstance(window, dict):
        return "승인 기간 미확인 · 실거래 시작 차단"
    return "\n".join(f"{display_field(key)}: {display_value(key, value)}" for key, value in window.items())


def _condition_lines(value: JsonObject, prefix: str) -> list[str]:
    rows: list[str] = []
    for key, item in value.items():
        if isinstance(item, dict):
            rows.append(prefix + display_field(key))
            rows.extend(_condition_lines(item, prefix + "  "))
        else:
            rows.append(f"{prefix}{display_field(key)}: {display_value(key, item)}")
    return rows
