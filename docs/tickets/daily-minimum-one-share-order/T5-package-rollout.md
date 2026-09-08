# T5: Frozen Safety, Packaging, and Rollout Evidence

**PRD Ref**: PRD-daily-minimum-one-share-order > US-5  
**Priority**: P0  
**Size**: M  
**Status**: Todo  
**Depends On**: T4

## 1. Objective

자격 증명 없는 feature-on frozen 진단으로 실주문 불가능성을 외부 ledger로 증명하고,
기본 false onedir를 빌드·감사한다. 실거래 활성은 별도 최종 사용자 승인까지 보류한다.

## 2. Acceptance Criteria

- [ ] automated/frozen QA clears credentials/LIVE env and uses temporary LOCALAPPDATA.
- [ ] sentinel transport fails any network/POST and external ledger remains zero.
- [ ] staged/deployed config remains `daily_minimum_order_enabled=false`.
- [ ] full onedir package audit and installed CLI diagnostic pass.
- [ ] no current live process/config/task is changed before final live rollout approval.

## 3. TDD Spec (Red Phase)

| # | Test Name | Type | Description | Expected |
|---|---|---|---|---|
| 1 | `test_frozen_daily_minimum_fixture_has_zero_transport_calls` | Package | sentinel coordinator | external ledger GET/POST 0 |
| 2 | `test_package_default_daily_minimum_disabled` | Package | staged config | false |
| 3 | `test_package_contains_all_daily_modules` | Package | onedir audit | no missing/private files |

### Test Files

- `tests/test_daily_minimum_packaging.py`
- `tests/test_auto_symbol_packaging.py`

## 4. Implementation Guide

| File | Change Type | Description |
|---|---|---|
| `nasdaq_auto_trader/frozen_diagnostic.py` | Modify | feature-on sentinel scenario |
| `nasdaq_auto_trader/package_audit.py` | Modify if required | module/config checks |
| `scripts/build_gui_exe.ps1` | Modify if required | frozen diagnostic invocation |
| `README.md` / `DESIGN.md` | Modify | opt-in, recovery, rollout contract |

## 5. Edge Cases

- Ambient credentials, inherited LIVE env, real LOCALAPPDATA, stale staging tree.
- Partial onedir replacement, schema migration before binary replacement.

## 6. Review Checklist

- [ ] Red observed
- [ ] Green observed
- [ ] Package audit clean
- [ ] Frozen external ledger proves no network/order
- [ ] Feature remains false pending final live approval
