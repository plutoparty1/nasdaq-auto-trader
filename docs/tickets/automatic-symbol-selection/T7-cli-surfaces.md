# T7: Read-Only and Automatic CLI Surfaces

**PRD Ref**: PRD-automatic-symbol-selection > US-5
**Priority**: P1 (High)
**Size**: M (2-4h)
**Status**: Done
**Depends On**: T4, T5, T6
**PRD AC**: AC-4.3, AC-5.3, AC-5.4

> The old loop-issued minute/cycle envelope was superseded on 2026-08-11 by
> the explicit `authorize-live-session` / `revoke-live-session` contract in
> `PRD-session-scoped-live-authorization.md`.

---

## 1. Objective

Expose read-only selection preview plus automatic once/loop execution while
retaining explicit live gates and one persistent session/claim store per loop.

## 2. Acceptance Criteria

- [ ] AC-1: `select-symbols --trading-config PATH` emits JSON, exits 0 for
  selected/no-trade and 2 for blocked, never accepts live confirmation, and
  makes zero order construction/submission calls.
- [ ] AC-2: `once` and `loop` accept `--auto-select`; live still requires
  `allow_live_trading=true` and `--confirm-live-orders` independently.
- [ ] AC-3: Live loop additionally requires a separately issued market-date
  authorization with a maximum of 12 actual order attempts, reuses one T5
  store, and blocks on session/date/attempt/binding failure.
- [ ] AC-4: Missing live flag, confirmation, or valid envelope returns the
  exact block reason, exits/terminates safely, and makes zero broker calls.
- [ ] AC-5: CLI output includes selection identity/reasons without secrets,
  account numbers, cash, or buying power.
- [ ] AC-6: Manual once/loop behavior remains unchanged without `--auto-select`.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_select_symbols_cli_exit_contract_and_zero_order_calls` | Integration | Selected/no-trade/blocked | 0/0/2, all order spies zero |
| 2 | `test_select_symbols_rejects_live_confirmation_argument` | CLI | Pass forbidden flag | Parser error |
| 3 | `test_auto_once_live_disabled_makes_zero_broker_calls` | Integration | `allow_live_trading=false` | Exact block |
| 4 | `test_auto_once_missing_confirmation_makes_zero_broker_calls` | Integration | Omit confirm flag | `live_order_confirmation_required` |
| 5 | `test_auto_loop_requires_session_authorization` | CLI | Missing/revoked authorization | Typed block |
| 6 | `test_auto_loop_reuses_state_and_blocks_on_attempt_limit` | Integration | Multi-cycle fake clock | No-order cycles free; 13th order attempt blocked |
| 7 | `test_cli_selection_output_masks_account_and_secret_values` | Unit | Serialize report/cycle | Sensitive fields absent |
| 8 | `test_manual_once_and_loop_contract_unchanged` | Regression | No auto flag | Existing output |

### 3.2 Test File Location

- `tests/test_auto_symbol_cli.py`
- Extend `tests/test_cli_dry_run_surface.py` and `tests/test_config_engine.py`.

### 3.3 Mock/Setup Required

- Fake selector/guard/store/broker with construction and submission spies.
- Fixed clock and in-memory sleep function for bounded loop tests.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/cli_parser.py` | Modify | Preview/auto/envelope arguments |
| `nasdaq_auto_trader/cli_main.py` | Modify | Dispatch and blocked exit contract |
| `nasdaq_auto_trader/cli_commands_special.py` | Modify | Read-only preview command |
| `nasdaq_auto_trader/cli_commands_basic.py` | Modify | Reused engine/store and bounded loop |
| `nasdaq_auto_trader/cli_formatters.py` | Modify | Sanitized selection report output |

### 4.2 Implementation Steps (Green Phase)

1. Add preview parser/dispatch/output with no order dependencies.
2. Add auto once wiring and independent existing live gates.
3. Add bounded loop envelope and one persistent store per command process.
4. Preserve manual branches and sanitize all new JSON output.

### 4.3 Refactor Phase

- Keep preview, once, and loop orchestration in small command helpers.

## 5. Edge Cases

- PRD E3, E7, E13, E20, E22.
- Missing confirmation independent of envelope, market-date/attempt block between cycles.

## 6. Review Checklist

- [ ] Red CLI/zero-broker tests fail before commands exist
- [ ] Green tests pass
- [ ] Refactor tests remain green
- [ ] Preview never constructs an order
- [ ] Existing live flag and confirmation remain independent gates
