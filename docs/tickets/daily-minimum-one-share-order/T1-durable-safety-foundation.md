# T1: Durable Safety Foundation

**PRD Ref**: PRD-daily-minimum-one-share-order > US-1, US-4, US-6  
**Priority**: P0  
**Size**: L  
**Status**: Todo  
**Depends On**: None

> Authorization storage and lifecycle are owned by the later approved
> `PRD-session-scoped-live-authorization.md`. This ticket extends that current
> market-date/actual-attempt envelope with the daily-minimum policy binding; it
> must not migrate or reuse the retired minute/cycle schema 1 authority.

## 1. Objective

일일 평가와 결과불명 상태를 canonical session store에 저장하고 기존 실거래 승인·계좌와
정확히 바인딩한다. 정상 주문과 최소주문 사이의 race 및 재시작 중복 POST를 막는다.

## 2. Acceptance Criteria

- [ ] schema 1 `trading_session.json`이 count/claims 보존 schema 2로 원자 migration된다.
- [ ] `EVALUATED_PREFLIGHT` claim과 `reserve_daily_post`의 0건 재확인·safety·intent·PMHS가 원자적이다.
- [ ] PMHS/ORDER_KNOWN/manual은 날짜·feature flag와 무관하게 모든 자동 POST를 차단한다.
- [ ] daily claim 자체는 이후 정상 보호주문을 차단하지 않는다.
- [ ] 과거 minute/cycle authorization schema 1은 feature flag와 무관하게 자동
  migration하지 않으며 명시적 시장일 재승인을 요구한다.
- [ ] feature/policy 변경은 기존 승인을 무효화한다.
- [ ] DPAPI-keyed HMAC account binding mismatch는 fail closed다.

## 3. TDD Spec (Red Phase)

| # | Test Name | Type | Description | Expected |
|---|---|---|---|---|
| 1 | `test_schema1_migrates_once_under_two_processes` | Integration | 동시 migration | 모든 count/ClaimStatus 보존, schema2 하나 |
| 2 | `test_daily_claim_and_normal_reservation_race` | Integration | barrier interleaving | daily POST와 선행 normal POST 동시 발생 0 |
| 3 | `test_claim_crash_consumes_only_daily_evaluation` | Integration | claim 직후 restart | daily 재평가 0, normal protective SELL 허용 |
| 4 | `test_post_started_blocks_all_dates_even_when_disabled` | Unit | unresolved global gate | 모든 자동 POST 0 |
| 5 | `test_retired_auth_schema_requires_reapproval_in_all_modes` | Unit | auth schema boundary | feature 상태와 무관하게 재승인 |
| 6 | `test_account_binding_is_install_keyed_and_exact` | Unit | DPAPI/HMAC | 계좌/설치 mismatch 차단 |

### Test Files

- `tests/test_daily_minimum_session_store.py`
- `tests/test_daily_minimum_authorization.py`
- `tests/test_daily_minimum_account_binding.py`

## 4. Implementation Guide

| File | Change Type | Description |
|---|---|---|
| `nasdaq_auto_trader/daily_minimum_types.py` | Create | strict state/token/value types |
| `nasdaq_auto_trader/daily_minimum_codec.py` | Create | schema/state parsing invariants |
| `nasdaq_auto_trader/trading_session_store.py` | Modify | schema2 migration and two-phase atomic methods |
| `nasdaq_auto_trader/live_authorization.py` | Modify | policy digest binding |
| `nasdaq_auto_trader/live_authorization_store.py` | Modify | current session-schema policy binding |
| `nasdaq_auto_trader/automatic_order_types.py` | Modify | policy/pre-reserved bindings |
| `nasdaq_auto_trader/account_binding.py` | Create | DPAPI-protected keyed HMAC |

### Green Steps

1. Add strict codecs/types and red migration tests.
2. Implement schema2 read/write and atomic claim/reserve methods with no I/O under lock.
3. Bind policy/account to authorization and tokens; reject regressions/future schemas.
4. Run targeted concurrency tests and existing session/authorization suites.

## 5. Edge Cases

- Corrupt/future/date-regressed state, interrupted write, lock timeout.
- Audit failure before PMHS versus crash after PMHS.
- Feature false while an unresolved state exists.

## 6. Review Checklist

- [ ] Red observed
- [ ] Green observed
- [ ] Refactor remains green
- [ ] Existing session/auth tests pass
- [ ] No raw account/order identifiers logged
