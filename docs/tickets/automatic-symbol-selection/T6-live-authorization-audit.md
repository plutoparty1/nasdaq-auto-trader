# T6: Live Readiness, Authorization, and Audit Guard

**PRD Ref**: PRD-automatic-symbol-selection > US-4
**Priority**: P0 (Blocker)
**Size**: L (4-8h)
**Status**: Done
**Depends On**: T4, T5
**PRD AC**: AC-1.3, AC-2.4, AC-4.1, AC-4.3, AC-4.7 through AC-4.9

> Authorization timing and consumption were superseded on 2026-08-11 by
> `PRD-session-scoped-live-authorization.md`: one NASDAQ market date and at
> most 12 actual order attempts. The audit, binding, and submission-gate
> requirements in this completed historical ticket remain normative.

---

## 1. Objective

Attach an automatic-order-only readiness/authorization/audit guard to the sole
`TradingEngine` broker path without changing manual or legacy order behavior.

## 2. Acceptance Criteria

- [ ] AC-1: A typed automatic-order context carries strategy/spec/universe/risk
  digests, signal timestamp, and mode. The added guard runs only when that
  context exists; manual and legacy AI paths retain current gates.
- [ ] AC-2: Immediately before broker access, live auto orders reread the
  promoted champion/spec and validate approval, digest, universe age,
  `allow_live_trading`, confirmation, and authorization envelope bindings.
- [ ] AC-3: Authorization accepts one NASDAQ market date and 1-12 actual order
  attempts; session/date/attempt exhaustion or binding change blocks the
  automatic loop. Read-only/no-order cycles do not consume the budget.
- [ ] AC-4: Intent audit append succeeds before the T5 order claim and broker;
  failure returns `audit_log_write_failed` with zero broker calls.
- [ ] AC-5: A granted T5 `submitting` claim is terminally updated from the
  broker response, and intent/outcome are distinct ordered audit events.
- [ ] AC-6: `TradingEngine` is the only submit owner; selector and AI Quant
  `LiveEngine` never receive a broker submission call for this feature.
- [ ] AC-7: Live rank-cache content is never accepted as order input and a
  current rerank failure blocks before this guard/broker.
- [ ] AC-8: Restored daily counts, cooldown, `daily_loss_breached`, and
  `daily_loss_state_unavailable` are checked before intent audit, claim, or
  broker. A block emits one sanitized `automatic_order_blocked` decision event
  but produces zero order-intent, claim, broker, or outcome calls.
- [ ] AC-9: T5 claim denial from lock, corruption, or persistence failure is a
  typed terminal block and cannot be ignored by the order guard.
- [ ] AC-10: Cross-process intent/outcome audit appends are serialized so every
  JSONL line is complete and parseable.
- [ ] AC-11: Sanitized `automatic_order_blocked` and
  `automatic_order_submitted` events include strategy/symbol/reason identity
  and elapsed milliseconds, while intent/outcome events contain no secrets or
  account values.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_auto_guard_reloads_champion_spec_and_stale_universe_before_broker` | Integration | Revoke/change/stale after rank | Exact block, broker zero |
| 2 | `test_live_authorization_envelope_checks_session_attempts_and_bindings` | Unit | Vary session/attempts/digests | Exact blocks |
| 3 | `test_auto_guard_call_order_is_readiness_audit_claim_broker_outcome` | Integration | Shared ordered ledger | Exact sequence |
| 4 | `test_intent_audit_failure_makes_zero_broker_and_claim_calls` | Integration | Failing append | `audit_log_write_failed` |
| 5 | `test_trading_engine_is_only_auto_submit_owner` | Integration | Engine/selector/LiveEngine spies | Engine one, others zero |
| 6 | `test_automatic_context_does_not_change_manual_live_or_dry_run_paths` | Regression | Context absent | Existing results unchanged |
| 7 | `test_same_rejected_claim_never_reaches_broker_twice` | Integration | Repeat terminal key | Second calls zero |
| 8 | `test_live_cache_rerank_failure_stops_before_order_guard` | Integration | Tamper cache, fail current data | All submit spies zero |
| 9 | `test_restored_safety_states_emit_block_event_before_order_side_effects` | Integration | Restart each persisted limit | Block event one; intent/claim/broker zero |
| 10 | `test_claim_lock_corruption_and_persistence_denials_block_broker` | Integration | Inject each T5 denial | Typed reason; broker/outcome zero |
| 11 | `test_spawned_auto_orders_with_real_claim_store_call_fake_broker_once` | Integration | Synchronized spawned workers | One file-backed broker record |
| 12 | `test_spawned_audit_writers_produce_only_complete_jsonl_events` | Integration | Concurrent intent/outcome writers | Every line parses and is complete |
| 13 | `test_order_events_are_named_timed_and_exclude_sensitive_values` | Integration | Blocked/submitted with injected secrets | Exact sanitized event schema |

### 3.2 Test File Location

- `tests/test_auto_symbol_live_guard.py`
- `tests/test_auto_symbol_live_audit.py`
- Extend `tests/test_config_engine.py` and `tests/test_ai_quant_live_integration.py`.

### 3.3 Mock/Setup Required

- Fake promoted/spec/universe stores, audit logger, T5 claim store, and broker.
- One ordered call ledger shared by all injected dependencies and fixed clocks.
- Spawn-safe top-level workers, synchronized barrier, file-backed fake broker,
  bounded joins, and forced cleanup for cross-process tests.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/live_authorization.py` | Create | Digest-bound bounded envelope |
| `nasdaq_auto_trader/automatic_order_guard.py` | Create | Readiness/audit/claim orchestration |
| `nasdaq_auto_trader/ai_quant_lab/audit_logger.py` | Modify | Cross-process serialized JSONL append |
| `nasdaq_auto_trader/engine_types.py` | Modify | Typed automatic-order provenance |
| `nasdaq_auto_trader/engine.py` | Modify | Inject guard/store/envelope |
| `nasdaq_auto_trader/engine_orders.py` | Modify | Guard only typed automatic orders |
| `nasdaq_auto_trader/engine_cycle.py` | Modify | Build automatic provenance context |

### 4.2 Implementation Steps (Green Phase)

1. Define typed automatic provenance and bounded authorization envelope.
2. Add fresh readiness and stale-universe validation.
3. Consume restored session safety blocks before intent audit.
4. Serialize audit append and order intent audit, T5 claim, broker call,
   terminal claim, outcome audit.
5. Treat every T5 denial as fail-closed and emit sanitized final order events.
6. Route only automatic-context orders through the new guard.

### 4.3 Refactor Phase

- Keep provenance, policy, and engine adapter separate and narrowly typed.

## 5. Edge Cases

- PRD E2, E13, E18-E20, E25, E26.
- Manual order with no artifact, audit disk full, terminal rejected claim.

## 6. Review Checklist

- [ ] Red ordering/authorization/audit tests fail first
- [ ] Green tests pass
- [ ] Refactor tests remain green
- [ ] Manual/legacy behavior remains unchanged
- [ ] Selector and AI Quant LiveEngine submit spies remain zero
- [ ] Full regression suite passes
