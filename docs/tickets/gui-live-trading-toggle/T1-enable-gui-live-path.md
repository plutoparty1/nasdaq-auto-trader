# T1: Enable the guarded GUI LIVE path

**PRD Ref**: PRD-gui-live-trading-toggle
**Priority**: P1
**Size**: M
**Status**: Done
**Depends On**: None

## Objective

Make the saved desktop LIVE setting reach the existing live engine while retaining every
independent production safety gate.

## Acceptance Criteria

- A live GUI controller can start and create a compatible engine factory.
- The factory receives `live_order_confirmation=True` in live mode and `False` otherwise.
- Missing environment authorization and credentials are rejected at controller start,
  before the real engine or broker client is created.
- The UI no longer claims all desktop LIVE actions are blocked.
- Cash-only and no-short protections are unchanged.

## TDD Spec

| Test | Type | Expected red condition |
|---|---|---|
| `test_gui_live_action_reaches_confirmed_engine_factory` | Unit | Current controller raises `gui_live_trading_disabled`. |
| `test_gui_dry_run_does_not_confirm_live_orders` | Unit | Factory confirmation propagation does not exist. |
| `test_gui_live_real_engine_requires_environment_authorization` | Integration | Existing engine validation must still fail closed before broker creation. |
| `test_live_banner_reports_guarded_live_mode` | Unit | Current banner says all desktop actions are blocked. |

Test file: `tests/test_gui_live_mode.py`

## Implementation Guide

- Modify `nasdaq_auto_trader/app_controller.py` to remove the blanket block and pass the
  mode-derived confirmation only to factories that support it.
- Modify `nasdaq_auto_trader/app_ui_render.py` to report guarded LIVE status.
- Update the README desktop LIVE statements.
- Do not alter broker, risk, cash, no-short, or credential validation code.

## Review Checklist

- [x] Red observed
- [x] Green observed
- [x] Full regression suite passes
- [x] EXE rebuilt and package audit passes
- [x] No real order submitted during QA
