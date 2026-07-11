# T4: TradingEngine Automatic-Selection Cycle

**PRD Ref**: PRD-automatic-symbol-selection > US-1, US-4
**Priority**: P1 (High)
**Size**: L (4-8h)
**Status**: Done
**Depends On**: T2, T3
**PRD AC**: AC-1.1 through AC-1.3, AC-4.1, AC-4.2, AC-4.6, AC-4.9

---

## 1. Objective

Integrate selected entry symbols into the existing `TradingEngine` while
preserving held-position exits, technical timing, risk settings, and aggregate
same-cycle buying-power limits.

## 2. Acceptance Criteria

- [ ] AC-1: Auto cycle order is load account/positions, resolve entry universe,
  union held symbols, fetch bars, rank entries, then evaluate rule decisions.
- [ ] AC-2: Entry candidates never read/fallback to manual ticker fields;
  blocked/no-trade selection submits zero entry orders.
- [ ] AC-3: Every held symbol is evaluated for a sell even when removed from
  the universe or absent from the entry shortlist.
- [ ] AC-4: A selected buy still requires `TechnicalStrategy`, `RiskManager`,
  settings, market-hours, and broker-response gates.
- [ ] AC-5: Accepted buys reserve cash, buying power, notional, exposure, and
  quantity before the next candidate; rejected buys reserve nothing.
- [ ] AC-6: Same-cycle sells do not increase spendable cash for later buys.
- [ ] AC-7: Cycle items expose one typed `SelectionReport` without changing
  manual-mode output or the disabled-by-default behavior.
- [ ] AC-8: Cycle completion/block emits sanitized `selection_completed` or
  `selection_blocked` with elapsed milliseconds and reason codes.
- [ ] AC-9: Invalid/stale live snapshots block before market-data client or
  broker construction; dry-run/paper retain the stale warning.
- [ ] AC-10: Dry-run uses only `DryRunBroker`; paper constructs only the paper
  endpoint and never a live client.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_auto_cycle_loads_positions_before_entry_bars` | Integration | Spy call order | Required sequence |
| 2 | `test_auto_cycle_never_reads_manual_entry_tickers` | Integration | Poison manual fields | Selected universe only |
| 3 | `test_held_symbol_outside_shortlist_is_evaluated_for_sell` | Integration | Held removed symbol | Sell decision path runs |
| 4 | `test_selected_buy_requires_technical_risk_settings_and_market_hours_gates` | Integration | Parameterize each blocking gate | Broker calls zero |
| 5 | `test_multiple_buys_reserve_cycle_start_resources` | Integration | Two valid buys | Aggregate caps enforced |
| 6 | `test_rejected_buy_does_not_reserve_and_sell_does_not_fund_buy` | Integration | Mixed responses | Conservative ledger |
| 7 | `test_manual_cycle_contract_is_unchanged_when_flag_false` | Regression | Existing fixture | Same result payload |
| 8 | `test_blocked_no_trade_and_live_rerank_failure_never_fallback` | Integration | Poison manual ticker in three failure modes | Broker spy zero |
| 9 | `test_invalid_stale_or_missing_frozen_snapshot_stops_before_clients` | Integration | Invalid/stale/missing repository | Market/broker constructors zero |
| 10 | `test_dry_run_and_paper_auto_cycle_never_construct_live_client` | Integration | Parameterized modes | Dry broker/paper URL only |
| 11 | `test_insufficient_buying_power_blocks_before_broker` | Integration | Buying power below one share | Broker calls zero, submitted false |
| 12 | `test_existing_position_with_additional_buy_disabled_blocks` | Integration | Already-held selected symbol | Broker spy zero |
| 13 | `test_rejected_response_with_id_is_not_submitted_or_reserved` | Integration | Rejected-with-ID response | Submitted false, no reservation |
| 14 | `test_cycle_events_record_completed_and_blocked_elapsed_time` | Unit | Both cycle outcomes | Sanitized typed events |

### 3.2 Test File Location

- `tests/test_auto_symbol_engine_cycle.py`
- `tests/test_auto_symbol_engine_reservations.py`
- Extend `tests/test_config_engine.py`.

### 3.3 Mock/Setup Required

- Fake selector, broker, market data, positions, account, and fixed clock.
- Broker responses for submitted, rejected-with-ID, and blocked cases.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/engine.py` | Modify | Inject selector/artifact/session dependencies |
| `nasdaq_auto_trader/engine_cycle.py` | Modify | Auto cycle orchestration and reservation ledger |
| `nasdaq_auto_trader/engine_portfolio.py` | Modify | Position-first symbol and bar loading |
| `nasdaq_auto_trader/engine_types.py` | Modify | Typed selection/cycle result |
| `nasdaq_auto_trader/config_runtime.py` | Modify | Auto-mode runtime compatibility |
| `nasdaq_auto_trader/broker_response.py` | Modify | Reservation-worthy accepted states if needed |

### 4.2 Implementation Steps (Green Phase)

1. Add injected selector and preserve the current manual branch unchanged.
2. Reorder only the auto branch and union held symbols before bar fetch.
3. Process ranked entries and held exits through existing rule/risk gates.
4. Add a local reservation snapshot updated only on accepted buys.

### 4.3 Refactor Phase

- Extract small auto-cycle helpers; keep `engine_cycle.py` below the project
  module-size ceiling.

## 5. Edge Cases

- PRD E7-E10, E12, E14-E16.
- Selected symbol already held, no bars for held symbol, rejected broker ID.

## 6. Review Checklist

- [ ] Red integration tests fail on current manual-only flow
- [ ] Green tests pass
- [ ] Refactor tests remain green
- [ ] Manual branch diff is minimal and regression-tested
- [ ] Selector/AI Quant LiveEngine never submits
- [ ] Full regression suite passes
