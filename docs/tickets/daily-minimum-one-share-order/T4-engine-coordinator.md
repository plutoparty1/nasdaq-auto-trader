# T4: Guarded Engine Coordinator and Operator Feedback

**PRD Ref**: PRD-daily-minimum-one-share-order > US-1..US-6  
**Priority**: P0  
**Size**: L  
**Status**: Todo  
**Depends On**: T1, T2, T3

## 1. Objective

자동 cycle에 대사-first·normal-strategy-first·daily-fallback 순서를 연결하고 기존
AutomaticOrderGuard, broker lease, audit, GUI 표면을 우회 없이 재사용한다.

## 2. Acceptance Criteria

- [ ] startup/cycle에서 unresolved reconciliation이 모든 주문보다 먼저 실행된다.
- [ ] 정상 전략 reservation이 있으면 fallback POST 0이다.
- [ ] minimum reuses the same authorization permit/context/begin-confirm-finish path and consumes the pre-reserved token once without a second authorization attempt.
- [ ] broker lease covers fresh preflight through POST; no blocking I/O occurs under store lock.
- [ ] audit/GUI expose stable safe fields and persistent manual warning only.
- [ ] feature off has zero new evaluation/GET/POST and unchanged public results except existing unresolved reconciliation.

## 3. TDD Spec (Red Phase)

| # | Test Name | Type | Description | Expected |
|---|---|---|---|---|
| 1 | `test_no_trade_candidate_submits_one_guarded_limit_order` | Integration | happy path fake KIS | POST 1, exact ledger order |
| 2 | `test_normal_order_wins_concurrent_fallback` | Integration | barrier race | fallback POST 0 |
| 3 | `test_lease_and_each_preflight_failure_consume_evaluation` | Integration | fault table | POST 0, no same-day retry |
| 4 | `test_post_crash_boundaries_never_retry` | Integration | process kill points | PMHS/manual, POST <=1 |
| 5 | `test_gui_safe_daily_minimum_feedback` | UI unit | evaluated/blocked/manual | no secret/raw response |

### Test Files

- `tests/test_daily_minimum_engine.py`
- `tests/test_daily_minimum_concurrency.py`
- `tests/test_daily_minimum_fault_injection.py`
- `tests/test_daily_minimum_gui.py`

## 4. Implementation Guide

| File | Change Type | Description |
|---|---|---|
| `nasdaq_auto_trader/daily_minimum_coordinator.py` | Create | cycle orchestration |
| `nasdaq_auto_trader/engine_automatic_cycle.py` | Modify | reconciliation and fallback ordering |
| `nasdaq_auto_trader/engine_orders.py` | Modify | pre-reserved guarded path and protective exit hook |
| `nasdaq_auto_trader/automatic_order_guard.py` | Modify | consume typed token without double reservation |
| `nasdaq_auto_trader/app_controller.py` | Modify | safe result summaries |
| `nasdaq_auto_trader/app_ui_actions.py` | Modify | persistent status/log feedback |

## 5. Edge Cases

- Approval expires between preflight and POST.
- Canary lease/known/manual/unmatched open order.
- Audit fsync failure, GET deadline, exact ID missing, GUI restart.

## 6. Review Checklist

- [ ] Red observed
- [ ] Green observed
- [ ] Guard/lease/audit paths are not bypassed
- [ ] Full existing order-safety suite passes
