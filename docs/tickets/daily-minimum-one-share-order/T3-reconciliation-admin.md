# T3: Ownership Reconciliation and Admin Recovery

**PRD Ref**: PRD-daily-minimum-one-share-order > US-2, US-4, US-6  
**Priority**: P0  
**Size**: L  
**Status**: Todo  
**Depends On**: T1

## 1. Objective

exact KIS order ID와 position equation으로 최소주문 소유권을 대사하고, 불명확 상태는
fail closed로 유지하며 감사된 수동 해제·구버전 rollback 표면을 제공한다.

## 2. Acceptance Criteria

- [ ] exact order/date/symbol/side/qty/price와 full-fill equation만 owned/complete를 만든다.
- [ ] absent/partial/history-incomplete/external observable contradiction은 manual terminal이다.
- [ ] zero-fill terminal reject/cancel/expire만 `COMPLETED_NO_FILL`이다.
- [ ] owned symbol BUY는 차단하고 guarded risk-reducing SELL은 daily reconciler에 연결한다.
- [ ] admin resolution/handoff는 keyed evidence만 저장하고 현재 승인을 무효화한다.
- [ ] rollback은 session v1 projection + auth v2 archive/removal + fresh approval을 강제한다.

## 3. TDD Spec (Red Phase)

| # | Test Name | Type | Description | Expected |
|---|---|---|---|---|
| 1 | `test_buy_fill_requires_exact_owned_equation` | Unit | 각 mismatch injection | owned 생성 0/manual |
| 2 | `test_day_zero_fill_and_partial_matrix` | Unit | terminal statuses | only zero-fill completes |
| 3 | `test_friday_owned_lot_survives_monday` | Integration | rollover | attempt reset, lot preserved |
| 4 | `test_guarded_protective_sell_updates_owned_lot` | Integration | fill/timeout/partial | remove/manual matrix |
| 5 | `test_admin_resolution_invalidates_authorization` | Integration | typed evidence | auth cleared, audit token only |
| 6 | `test_rollback_projection_loads_previous_parser` | Compatibility | stopped process fixture | v1 loads, auth requires fresh approval |

### Test Files

- `tests/test_daily_minimum_reconciliation.py`
- `tests/test_daily_minimum_admin.py`
- `tests/test_daily_minimum_rollback.py`

## 4. Implementation Guide

| File | Change Type | Description |
|---|---|---|
| `nasdaq_auto_trader/daily_minimum_reconcile.py` | Create | exact typed reconciliation |
| `nasdaq_auto_trader/daily_minimum_admin.py` | Create | resolution/handoff/rollback |
| `nasdaq_auto_trader/brokers/kis_reconciliation.py` | Modify | typed terminal/filled/remaining fields |
| `nasdaq_auto_trader/cli_parser.py` | Modify | explicit admin commands |
| `nasdaq_auto_trader/cli_main.py` | Modify | safe admin dispatch |

## 5. Edge Cases

- History pagination gap/deadline/retention boundary.
- Same-symbol external order, position mismatch, account change.
- Manual acknowledgement without evidence, active/open order during rollback.

## 6. Review Checklist

- [ ] Red observed
- [ ] Green observed
- [ ] Unknown POST is never auto-cleared
- [ ] Rollback cannot reuse authorization

