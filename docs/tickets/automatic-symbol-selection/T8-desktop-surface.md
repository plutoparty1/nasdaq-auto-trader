# T8: Desktop Automatic-Selection Surface

**PRD Ref**: PRD-automatic-symbol-selection > US-5
**Priority**: P1 (High)
**Size**: M (2-4h)
**Status**: Done
**Depends On**: T4, T5
**PRD AC**: AC-4.4, AC-4.7, AC-5.1, AC-5.2, AC-5.6

---

## 1. Objective

Add one persisted auto-selection toggle and plain Korean selection state to the
desktop dry-run/paper workflow while making GUI live execution impossible.

## 2. Acceptance Criteria

- [ ] AC-1: Settings show `과거 데이터 기반 종목 자동 선택`, retain widget
  references, and disable manual ticker and AI candidate widgets only while on.
- [ ] AC-2: Toggle state round-trips through existing settings without changing
  manual defaults or unrelated values.
- [ ] AC-3: GUI controller/action accepts automatic dry-run and paper cycles but
  rejects `mode=live` before broker construction or submission, even if the
  underlying action is invoked directly.
- [ ] AC-4: No new live start/execute button, menu, callback, or shortcut exists.
- [ ] AC-5: Dashboard renders universe date, resolved strategy, shortlist,
  symbols, scores/reasons, and `학습 완료 전략 없음`/block reasons in Korean.
- [ ] AC-6: Three operational blocks create persistent visible error state;
  repeated `no_trade` remains normal and does not pause or fallback.
- [ ] AC-7: Legacy LLM direct-order behavior remains `ai_direct_order_disabled`.
- [ ] AC-8: Desktop dry-run/paper cycles reuse the T5 persistent store so daily
  counts and cooldown survive controller/application restart.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_auto_toggle_round_trips_and_traces_manual_widget_state` | GUI unit | Toggle twice | Exact widget states |
| 2 | `test_gui_auto_live_action_blocks_before_broker_construction` | Integration | Load live settings, invoke action | GUI block, constructors/submits zero |
| 3 | `test_gui_auto_dry_run_and_paper_actions_reach_controller` | Integration | Safe modes | Selection report rendered |
| 4 | `test_gui_exposes_no_live_auto_control_or_callback` | Contract | Inspect fields/actions | No live surface |
| 5 | `test_selection_report_renders_plain_korean_readiness_and_reasons` | Unit | Selected/no-trade/blocked | Required copy |
| 6 | `test_no_trade_does_not_increment_operational_block_streak` | Controller | Repeated no-trade | Continues normally |
| 7 | `test_three_operational_blocks_persist_error_until_success` | Controller | Block/block/block/success | Error then clears |
| 8 | `test_legacy_ai_direct_order_remains_blocked` | Regression | Existing AI fixture | Same reason |
| 9 | `test_gui_paper_counts_and_cooldown_survive_controller_restart` | Integration | Restart with same state path | Restored settings guard block |

### 3.2 Test File Location

- `tests/test_auto_symbol_gui.py`
- `tests/test_auto_symbol_presenter.py`
- Extend `tests/test_app_controller.py` and `tests/test_ai_engine_decision.py`.

### 3.3 Mock/Setup Required

- Existing Tk variable/control stubs with state trace callbacks.
- Fake controller, selector reports, broker constructor/submission spies.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/settings_window_fields_core.py` | Modify | Manual ticker field reference |
| `nasdaq_auto_trader/settings_window_fields_advanced.py` | Modify | Toggle and candidate reference |
| `nasdaq_auto_trader/settings_window_dialog.py` | Modify | Widget state ownership/trace |
| `nasdaq_auto_trader/app_controller.py` | Modify | Safe modes and block streak |
| `nasdaq_auto_trader/trading_session_store.py` | Modify | Desktop store injection boundary if needed |
| `nasdaq_auto_trader/app_ui_actions.py` | Modify | Auto dry-run/paper action wiring |
| `nasdaq_auto_trader/app_ui_render.py` | Modify | Korean report presentation |

### 4.2 Implementation Steps (Green Phase)

1. Add referenced toggle/manual widgets and persisted state trace.
2. Inject one persistent T5 store into repeated desktop engine/controller cycles.
3. Block live mode at the GUI action/controller boundary before clients.
4. Render typed reports and distinguish operational block from no-trade.
5. Preserve legacy AI and manual settings behavior.

### 4.3 Refactor Phase

- Centralize Korean reason mapping without changing domain reason codes.

## 5. Edge Cases

- PRD E7, E14, E22.
- Direct callback invocation, no display/Tk stubs, settings reload while toggled.

## 6. Review Checklist

- [ ] Red UI/controller tests fail first
- [ ] Green tests pass
- [ ] Refactor tests remain green
- [ ] GUI live constructor and broker spies remain zero
- [ ] Manual and legacy AI regressions pass
- [ ] Full regression suite passes
