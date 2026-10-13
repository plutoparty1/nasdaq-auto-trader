from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from .ai_quant_lab.types import JsonObject
from .live_authorization import broker_authorization_digest
from .market_hours import regular_market_session
from .models import AccountSnapshot
from .production_fees import FeeScheduleInput, parse_fee_schedule
from .production_runtime import ProductionRuntime, load_runtime
from .production_sizing import candidate_plan


class StartService(Protocol):
    runtime: ProductionRuntime
    def preflight(self) -> JsonObject: ...
    def shutdown(self) -> JsonObject: ...
    def authorize(self, confirmation: str, review_digest: str) -> JsonObject: ...
    def start_live(self) -> JsonObject: ...
    def status(self) -> JsonObject: ...


def approval_window(now: datetime) -> JsonObject:
    session = regular_market_session(now)
    expiry = datetime.fromisoformat(session.closes_at).astimezone(ZoneInfo("Asia/Seoul")).isoformat() if session.closes_at else ""
    return {"duration": "one_US_regular_market_session;no_automatic_renewal",
            "market_date": now.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
            "expires_at_kst": expiry, "expires_at": expiry, "maximum_order_attempts": 12,
            "duration_hours": max(0.0, (datetime.fromisoformat(session.closes_at) - now).total_seconds() / 3600) if session.closes_at else 0,
            "expiry_behavior": "모든 주문 차단 · 읽기 전용 감시와 대사 계속 · 자동 갱신 없음",
            "after_expiry": "all_order_submissions_blocked;readonly_monitoring_reconciliation_continue",
            "protective_sells": "allowed_only_while_approval_and_other_checks_remain_valid"}


def prepare_start(service: StartService) -> JsonObject:
    state = service.status()
    if state.get("mode") == "live" and state.get("status") == "running":
        return {"status": "blocked", "blockers": ["live_operation_already_running"]}
    if state.get("mode") == "dry_run" and state.get("status") == "running":
        _ = service.shutdown()
    checked = service.preflight()
    value = checked.get("account")
    plan: JsonObject = {}
    if isinstance(value, dict):
        equity, cash, power = value.get("equity"), value.get("cash"), value.get("buying_power")
        if (isinstance(equity, int | float) and not isinstance(equity, bool)
            and isinstance(cash, int | float) and not isinstance(cash, bool)
            and isinstance(power, int | float) and not isinstance(power, bool)):
            base = load_runtime(service.runtime.app_dir, service.runtime.original_data, service.runtime.executable)
            plan = candidate_plan(base, AccountSnapshot(float(cash), float(equity), float(power)))
    return {**checked, "automatic_plan": plan,
            "before_after": plan, "approval_window": approval_window(datetime.now(UTC)),
            "fee_instructions": ["한국투자증권 HTS/MTS 또는 고객센터에서 이 계좌의 미국주식 적용 매수·매도 수수료율, 건별 최소 수수료, 매도 세금·제비용을 확인하세요.",
                                 "계좌별 할인·이벤트와 적용 기간, 확인한 자료를 출처에 적으세요. 세금 최소액·추가 비용 등 입력 모형에 없는 비용이 있으면 승인하지 말고 별도 확인이 필요합니다."]}


def configure_fee_profile(service: StartService, profile: FeeScheduleInput) -> JsonObject:
    if service.status().get("status") == "running":
        return {"status": "blocked", "blockers": ["stop_operation_before_draft_change"]}
    account_digest = broker_authorization_digest(service.runtime.config)
    payload: JsonObject = {"commission_rate": profile.commission_rate, "minimum_fee_usd": profile.minimum_fee_usd,
               "tax_rate": profile.tax_rate, "source": profile.source, "confirmed": True,
               "source_kind": profile.source_kind, "effective_from": profile.effective_from,
               "effective_to": profile.effective_to, "currency": "USD",
               "verification_method": "manual_user_verified",
               "account_digest": account_digest,
               "reviewed_at": datetime.now(UTC).isoformat()}
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    if parse_fee_schedule(encoded, account_digest) is None:
        return {"status": "blocked", "bl