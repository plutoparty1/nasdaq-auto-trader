# T3: Market Shortlist, Exchange Identity, and Cache

**PRD Ref**: PRD-automatic-symbol-selection > US-3
**Priority**: P1 (High)
**Size**: L (4-8h)
**Status**: Done
**Depends On**: T1, T2
**PRD AC**: AC-3.1 through AC-3.5, AC-4.9, AC-5.4

---

## 1. Objective

Produce a bounded, tradeable provider shortlist and a non-live selection cache
without allowing malformed provider data or cached symbols to authorize orders.

## 2. Acceptance Criteria

- [ ] AC-1: KIS uses the official overseas trading-value/liquidity response,
  intersects it with the snapshot, preserves provider rank, and caps at 30.
- [ ] AC-2: KIS validates the `NAS` price and `NASD` order identity before any
  ranking, bars, quote, buying-power, or order path is used.
- [ ] AC-3: A single `EGW00201` receives the existing bounded retry; repeated,
  partial, duplicate, or malformed responses block the whole shortlist.
- [ ] AC-4: Alpaca may batch bars but applies the same history, positive-price,
  dollar-volume, spread, staleness, and outlier rules.
- [ ] AC-5: Cache keys include provider/mode/universe/strategy/spec and registry
  digests/session date/limit; mismatch or corruption forces recomputation.
- [ ] AC-6: Preview, dry-run, and paper may reuse a 15-minute atomic cache;
  live never reads cached ranks or selected symbols as order input.
- [ ] AC-7: Cache serialization excludes credentials and account values.
- [ ] AC-8: Shortlist/cache operations emit typed `universe_loaded`,
  `liquidity_shortlist_created`, and `selection_cache_used` events with elapsed
  milliseconds, counts, identities, and no account values.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_kis_liquidity_intersection_preserves_rank_and_limit` | Unit | Parse ranked fixture | Ordered max-30 intersection |
| 2 | `test_kis_exchange_identity_mismatch_blocks_before_http` | Unit | Wrong price/order code | Zero transport calls |
| 3 | `test_kis_single_egw00201_retries_once_then_succeeds` | Unit | Rate limit then valid payload | Two transport calls, ordered result |
| 4 | `test_kis_timeout_duplicate_partial_and_malformed_payloads_fail_whole_shortlist` | Unit | Table-driven error fixtures | Exact calls, no partial shortlist |
| 5 | `test_market_quality_rules_reject_price_history_volume_spread_stale_and_outlier` | Unit | One case per rule | Exact symbol/reason removal |
| 6 | `test_selection_cache_identity_ttl_and_corrupt_json_recompute_or_block` | Unit | Change fields/corrupt JSON | Cache miss then recompute/block |
| 7 | `test_live_selector_ignores_modified_rank_cache` | Integration | Tamper selected symbol | Fresh ranking only |
| 8 | `test_live_cache_tamper_and_rerank_failure_never_constructs_order` | Integration | Tamper cache and fail current data | Broker/order spies zero |
| 9 | `test_cache_json_contains_no_secret_or_account_fields` | Unit | Serialize report | Sensitive fields absent |
| 10 | `test_alpaca_quote_batch_is_single_call_and_malformed_fails_closed` | Unit | Complete/incomplete snapshots | One batch; malformed blocks |
| 11 | `test_shortlist_and_cache_events_have_timing_without_secrets` | Unit | Run load/shortlist/cache | Typed sanitized events |

### 3.2 Test File Location

- `tests/test_auto_symbol_kis_shortlist.py`
- `tests/test_auto_symbol_market_quality.py`
- `tests/test_auto_symbol_cache.py`

### 3.3 Mock/Setup Required

- Fake KIS transport with call counter and retry sequence.
- Temporary atomic cache path and fixed market/session clocks.
- Fake Alpaca multi-symbol bar provider.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/brokers/kis_market.py` | Modify | Liquidity ranking parser/request |
| `nasdaq_auto_trader/brokers/kis_client.py` | Modify | Expose shortlist and exchange identity |
| `nasdaq_auto_trader/brokers/alpaca.py` | Modify | Typed batch latest-quote/snapshot input |
| `nasdaq_auto_trader/config.py` | Modify | Nasdaq KIS identity validation helper |
| `nasdaq_auto_trader/quant_data/market_quality.py` | Create | Provider-neutral tradability filters |
| `nasdaq_auto_trader/quant_data/selection_cache.py` | Create | Typed atomic non-live cache |
| `nasdaq_auto_trader/quant_data/symbol_selector.py` | Modify | Shortlist/cache integration boundary |

### 4.2 Implementation Steps (Green Phase)

1. Lock exchange identity before adding any new KIS request.
2. Add strict KIS response parsing and ordered snapshot intersection.
3. Add provider-neutral quality checks and strict Alpaca quote batching.
4. Add identity-bound atomic cache and hard live bypass.
5. Emit sanitized shortlist/cache timing events through the existing audit API.

### 4.3 Refactor Phase

- Keep HTTP parsing, quality policy, and cache policy in separate modules.

## 5. Edge Cases

- PRD E5, E6, E11, E16, E17, E19, E26.
- Unknown exchange alias, stale cache with valid JSON, empty intersection.

## 6. Review Checklist

- [ ] Red tests fail before adapters/cache exist
- [ ] Green tests pass
- [ ] Refactor tests remain green
- [ ] Live cache-tamper test proves fresh ranking
- [ ] No real HTTP calls in tests
- [ ] Full regression suite passes
