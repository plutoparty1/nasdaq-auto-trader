# T3: Risk-Managed Order Construction

**PRD Ref**: PRD-nasdaq-auto-trader > US-3
**Priority**: P1 (High)
**Size**: M (2-4h)
**Status**: Done
**Depends On**: T2

---

## 1. Objective

Ensure strategy decisions cannot bypass account-level and per-trade risk caps.

## 2. Acceptance Criteria

- [x] AC-1: Buy orders respect max position percentage.
- [x] AC-2: Buy orders respect cash buffer and buying power.
- [x] AC-3: Buy orders respect fixed-fraction risk sizing when available.
- [x] AC-4: Sell orders require an existing positive position.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_risk_manager_caps_buy_notional` | Unit | Max position cap works | PASS |
| 2 | `test_risk_manager_uses_per_trade_risk_distance` | Unit | Risk distance caps notional | PASS |
| 3 | `test_engine_dry_run_can_submit_to_injected_broker` | Integration | Engine submits to fake broker | PASS |

### 3.2 Test File Location

- `tests/test_indicators_strategy.py`
- `tests/test_config_engine.py`

### 3.3 Mock/Setup Required

- Fake broker and fake market data.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/risk.py` | Modify | Add risk-per-trade sizing |
| `nasdaq_auto_trader/engine.py` | Modify | Pass decision latest price/risk distance |
| `config.example.json` | Modify | Expose `risk_per_trade_pct` |

### 4.2 Implementation Steps

1. Add `risk_per_trade_pct`.
2. Compute notional from risk budget and stop distance.
3. Take the minimum of all applicable caps.

### 4.3 Refactor Phase

- Keep broker-neutral order type unchanged.

## 5. Edge Cases

- Missing or zero risk distance falls back to portfolio/cash caps.
- Notional below minimum suppresses order.

## 6. Review Checklist

- [x] Red: Risk-cap tests exposed changed expectations
- [x] Green: Tests pass after separating cap scenarios
- [x] Refactor: Risk helper isolated
- [x] AC all met
- [x] Existing tests not broken
- [x] Code style followed
- [x] No unnecessary changes
