# T3: Controller and GUI Integration

**PRD Ref**: US-1, US-2, US-3
**Priority**: P1
**Size**: M
**Status**: Todo
**Depends On**: T1, T2

## Acceptance Criteria

- Missing strategy during market hours runs shadow scan and keeps automation alive.
- Trading-ready health still routes to the existing live-trading cycle.
- GUI logs scan counts, report path, and zero submitted orders.

## TDD Spec

| Test | Red condition | Expected |
|---|---|---|
| `test_open_market_missing_strategy_runs_shadow_scan_without_pausing` | model absence safe-halts | scan and running state |
| `test_open_market_non_model_failure_still_safe_halts` | all failures shadow-scan | safe halt |
| `test_before_open_missing_model_stays_ready_for_opening_scan` | pre-open pauses | pre-market state |
| `test_shadow_scan_feedback_confirms_zero_orders` | no GUI feedback | count/path/zero orders |

Files: `automation_coordinator.py`, `controller_operations.py`,
`app_controller.py`, `app_ui_render.py`, plus tests. Scanner request failures map
to `market_data_unavailable` and pause. Existing live-ready routing and all
engine-side broker/account/order safety checks remain unchanged.
