# T2: Candidate, Time, and Quote Policy

**PRD Ref**: PRD-daily-minimum-one-share-order > US-1, US-3  
**Priority**: P1  
**Size**: M  
**Status**: Todo  
**Depends On**: T1

## 1. Objective

공개 selection 계약을 바꾸지 않고 승인 전략의 임계값 전 후보를 계산하고, 정확한 시장
시간창·호가·Decimal tick 정책으로 BUY/SELL 1주 결정을 만든다.

## 2. Acceptance Criteria

- [ ] `SelectionReport` 직렬화는 feature-off에서 불변이다.
- [ ] 내부 prethreshold tuple은 score desc/symbol asc와 aware signal timestamp를 가진다.
- [ ] window는 `[close-60m, min(buy-stop, close))`다.
- [ ] setting `daily_minimum_max_spread_bps=50`, range 1..500, inclusive 공식이 적용된다.
- [ ] BUY ask ceiling, SELL bid floor, 5초 deadline, invalid-candidate skip 규칙이 결정적이다.

## 3. TDD Spec (Red Phase)

| # | Test Name | Type | Description | Expected |
|---|---|---|---|---|
| 1 | `test_prethreshold_candidates_do_not_change_public_report` | Contract | feature off | golden bytes 불변 |
| 2 | `test_fallback_window_exchange_boundaries` | Unit | DST/early-close/1us | exact inclusive/exclusive 결과 |
| 3 | `test_quote_price_examples` | Unit | PRD 표 fixtures | exact Decimal limit/reason |
| 4 | `test_spread_boundary_and_digest_change` | Unit | below/equal/above | equal 허용, 변경 승인 무효 |
| 5 | `test_invalid_quote_skips_but_timeout_stops` | Unit | candidate sequence | 정책대로 call ledger 고정 |

### Test Files

- `tests/test_daily_minimum_policy.py`
- `tests/test_daily_minimum_pricing.py`
- `tests/test_daily_minimum_selection.py`

## 4. Implementation Guide

| File | Change Type | Description |
|---|---|---|
| `nasdaq_auto_trader/daily_minimum_policy.py` | Create | pure decision/time policy |
| `nasdaq_auto_trader/daily_minimum_pricing.py` | Create | Decimal quote oracle |
| `nasdaq_auto_trader/automatic_selection.py` | Modify | internal prethreshold result |
| `nasdaq_auto_trader/quant_data/symbol_selector.py` | Modify | generate both rankings once |
| `nasdaq_auto_trader/config_settings.py` | Modify | opt-in and spread settings |
| `nasdaq_auto_trader/config_validation.py` | Modify | validated ranges |

## 5. Edge Cases

- Holiday, early close, DST, naive clock, clock regression, start after endpoint.
- Zero/NaN/infinite/crossed/wide quote, sub-dollar tick, exact-cent cash boundary.

## 6. Review Checklist

- [ ] Red observed
- [ ] Green observed
- [ ] Public report contract unchanged
- [ ] No float used for order price normalization

