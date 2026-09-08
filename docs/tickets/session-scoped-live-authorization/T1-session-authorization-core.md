# T1: 세션 승인 모델·저장소·주문 가드

**PRD Ref**: PRD-session-scoped-live-authorization > US-1, US-2, US-3
**Priority**: P0 (Blocker)
**Size**: M (2-4h)
**Status**: Done
**Depends On**: None

---

## 1. Objective

60분/평가주기 기반 schema 1 승인을 한 NASDAQ 거래일과 최대 12개 실제 주문 의도에
결합된 schema 2 승인으로 교체한다. 장 밖·다음 거래일·승인 교체·binding 변경에서는
기존 주문 안전 경로가 broker POST 전에 fail-closed해야 한다.

## 2. Acceptance Criteria

- [x] AC-1: `authorization_market_date`가 장 전/장중에는 당일, close/휴일/주말에는 다음
  예정 NASDAQ 거래일을 반환하고 naive datetime은 typed block한다.
- [x] AC-2: schema 2는 발급별 `authorization_id`, `market_date`, broker/strategy/universe/
  risk binding, `attempts/max_attempts`를 원자 저장하고 schema 1은 재승인 필요로 차단한다.
- [x] AC-3: `start_cycle` reload는 평가주기를 소비하지 않으며 유효 승인 장 밖에서도
  selection을 막지 않는다.
- [x] AC-4: `begin`만 attempt를 원자 소비하고 12번째까지 허용, 13번째·장 밖·다음날은
  소비/POST 0이다. 소비 성공 뒤 실패나 crash에서도 attempt는 rollback하지 않는다.
- [x] AC-5: `confirm`은 현재 파일과 `authorization_id` 포함 전체 binding 및 현재 정규장을
  다시 검증하고 교체/삭제/close이면 claim REJECTED, POST 0이다.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
|---|---|---|---|---|
| 1 | `test_authorization_market_date_uses_current_or_next_session` | Unit | 장 전/장중/close/주말/조기폐장/DST | 정확한 date, naive typed error |
| 2 | `test_schema_two_round_trip_and_schema_one_reapproval` | Integration | 실제 임시 파일 저장소 재개 | attempt 보존, schema1 typed block |
| 3 | `test_start_cycle_reload_does_not_consume_attempt` | Integration | 78회 reload와 실행 중 승인 교체 | attempts 0, 최신 세대 반영 |
| 4 | `test_only_begin_consumes_twelve_attempts_atomically` | Integration | 독립 store 인스턴스 동시 소비 | 최대 12, 13번째 차단 |
| 5 | `test_outside_session_and_next_date_do_not_consume` | Unit | open 전/close/다음 거래일 begin | attempt 0, typed block |
| 6 | `test_confirm_rejects_same_binding_new_authorization_id` | Integration | begin 뒤 같은 binding 재발급 | claim REJECTED, POST 0 |
| 7 | `test_committed_attempt_is_monotonic_when_later_gate_fails` | Integration | audit/claim 전 실패 주입 | attempt 1, POST 0 |

### 3.2 Test File Location

- `tests/test_market_hours.py`
- `tests/test_live_authorization_lifecycle.py`
- `tests/test_auto_symbol_authorization_risk.py`
- `tests/test_auto_symbol_order_time_rechecks.py`

### 3.3 Mock/Setup Required

- aware injected clock, `tempfile.TemporaryDirectory`, 실제 `LiveAuthorizationStore`
- 기존 `NullAuditLogger`, fake broker와 실제 `TradingSessionStore`
- 네트워크와 실거래 환경변수는 사용하지 않는다.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
|---|---|---|
| `nasdaq_auto_trader/market_hours.py` | Modify | target market date와 정규장 oracle |
| `nasdaq_auto_trader/live_authorization.py` | Modify | schema 2 typed envelope와 broker binding |
| `nasdaq_auto_trader/live_authorization_store.py` | Modify | schema2 codec/load/issue/consume/validate/archive |
| `nasdaq_auto_trader/automatic_order_guard.py` | Modify | reload-only cycle, begin consume, confirm recheck |
| `nasdaq_auto_trader/engine.py` | Modify | 암묵 승인 생성 제거 |

### 4.2 Implementation Steps (Green Phase)

1. 달력 경계와 schema 2 codec/파일 lock 테스트를 최소 구현으로 통과시킨다.
2. guard reload/begin/confirm 상태 전이를 기존 reservation/audit/claim 순서에 연결한다.
3. 엔진 생성자에서 승인 생성 파라미터와 암묵 발급을 제거하고 load-only를 검증한다.

### 4.3 Refactor Phase

- codec 확장으로 250 pure LOC를 넘으면 schema codec을 별도 책임 모듈로 분리한다.

## 5. Edge Cases

- E1~E14, E18~E22 전부. 특히 close excluded, schema1 reapproval, 같은 binding의 새
  authorization_id, attempt-commit crash를 직접 검증한다.

## 6. Review Checklist

- [x] Red: 테스트 실행 → FAILED 확인됨
- [x] Green: 테스트 실행 → PASSED 확인됨
- [x] Refactor: 테스트 실행 → PASSED 유지 확인됨
- [x] AC 전부 충족
- [x] 기존 테스트 깨지지 않음
- [x] 코드 스타일 준수
- [x] 불필요한 변경 없음
