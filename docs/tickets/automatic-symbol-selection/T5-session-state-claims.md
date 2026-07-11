# T5: Persistent Session State and Order Claims

**PRD Ref**: PRD-automatic-symbol-selection > US-4
**Priority**: P0 (Blocker)
**Size**: L (4-8h)
**Status**: Done
**Depends On**: T1
**PRD AC**: AC-4.6, AC-4.7, AC-5.4

---

## 1. Objective

Persist automatic-trading counters and at-most-once signal claims safely across
loops, Windows processes, and crashes without storing account values.

## 2. Acceptance Criteria

- [ ] AC-1: Daily order counts, cooldown timestamp, market date, breach latch,
  and signal claims persist atomically without account numbers, balances,
  buying power, credentials, or raw starting equity.
- [ ] AC-2: A same-day restart with `daily_loss_breached=true` stays blocked. If
  a prior baseline existed but cannot be reconstructed from an authoritative
  broker value, automatic live buys fail closed with
  `daily_loss_state_unavailable` until the next market day.
- [ ] AC-3: Under an inter-process lock, a signal key transitions `new` to
  persisted `submitting` before the broker and then to a terminal state.
- [ ] AC-4: `submitting` recovered after a crash becomes terminal `uncertain`;
  `submitted`, `rejected`, and `uncertain` never auto-retry the same key.
- [ ] AC-5: The key includes market date, strategy ID/version, symbol, side,
  and signal timestamp; a retry after reconciliation requires a new signal
  timestamp/idempotency key.
- [ ] AC-6: Lock timeout, malformed state, and write/flush/replace failure return
  typed fail-closed results and never grant a claim.
- [ ] AC-7: New-market-day reset preserves unresolved/submitted claim history
  required for reconciliation while resetting daily counters/latches.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_session_counts_and_cooldown_survive_store_reopen` | Unit | Persist/reload | Exact non-sensitive state |
| 2 | `test_daily_loss_breach_and_unavailable_baseline_fail_closed_after_restart` | Unit | Restart breached/below-limit states | Latch block or unavailable block |
| 3 | `test_state_json_contains_no_account_values_or_credentials` | Unit | Inspect serialization | Sensitive values absent |
| 4 | `test_concurrent_spawn_processes_claim_signal_once` | Integration | Synchronized Windows-spawn race | Exactly one claim granted |
| 5 | `test_crash_window_recovers_submitting_as_uncertain` | Integration | Simulate crash points | No automatic retry |
| 6 | `test_submitted_and_rejected_keys_block_after_store_reopen` | Integration | Reopen and reclaim same key | Claim denied |
| 7 | `test_idempotency_key_field_and_new_timestamp_matrix` | Unit | Mutate every required field | Only genuine new key differs |
| 8 | `test_store_write_replace_fsync_and_lock_fail_closed` | Unit | Inject storage failures | Typed denial, no grant |
| 9 | `test_malformed_ledger_never_resets_to_empty` | Unit | Corrupt persisted JSON | Typed denial |
| 10 | `test_market_day_reset_preserves_terminal_claims` | Unit | Advance Eastern date | Counters reset, claims retained |

### 3.2 Test File Location

- `tests/test_auto_symbol_session_store.py`
- `tests/test_auto_symbol_idempotency.py`

### 3.3 Mock/Setup Required

- Temporary state/lock files and fixed clocks.
- Spawn-safe top-level workers, synchronized start barrier, process-safe
  file-backed result ledger, bounded joins, and forced cleanup on timeout.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/trading_session_store.py` | Create | Atomic persistent counters and claims |
| `nasdaq_auto_trader/config_settings.py` | Modify | Serializable session-state contract |
| `nasdaq_auto_trader/session_claims.py` | Create | Typed keys and claim state machine |

### 4.2 Implementation Steps (Green Phase)

1. Define minimal non-sensitive persisted state and typed claim transitions.
2. Implement Windows-safe inter-process locking and atomic replace/flush.
3. Add conservative daily-loss latch/unavailable-baseline restart behavior.
4. Add spawn-safe race, crash, corruption, and storage-failure tests.

### 4.3 Refactor Phase

- Keep lock/storage mechanics separate from claim and daily-limit policy.

## 5. Edge Cases

- PRD E21, E25.
- Disk full, stale lock owner, malformed state, rejected/submitted persisted key.

## 6. Review Checklist

- [ ] Red concurrency/crash/storage tests fail first
- [ ] Green tests pass
- [ ] Refactor tests remain green
- [ ] State contains no secrets/account values
- [ ] Full regression suite passes
