# T4: Backtest Metrics And Execution Model

**PRD Ref**: PRD-nasdaq-auto-trader > US-4
**Priority**: P1 (High)
**Size**: L (4-8h)
**Status**: Done
**Depends On**: T2, T3

---

## 1. Objective

Make the CSV backtester more useful for strategy research by reducing same-bar
look-ahead bias and reporting risk metrics.

## 2. Acceptance Criteria

- [x] AC-1: Signals use known close data and execute at next bar open.
- [x] AC-2: Equity curve is recorded.
- [x] AC-3: Return, max drawdown, Sharpe ratio, trade count, and win rate are
  exposed.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_backtester_reports_risk_metrics_and_next_open_trade` | Unit | Backtester reports metrics and delayed execution | PASS |

### 3.2 Test File Location

- `tests/test_config_engine.py`

### 3.3 Mock/Setup Required

- Synthetic monotonic bars.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/backtest.py` | Modify | Event loop, pending orders, metrics |
| `nasdaq_auto_trader/cli.py` | Modify | Print new backtest metrics |

### 4.2 Implementation Steps

1. Build timestamp-ordered event loop.
2. Execute pending orders at next open.
3. Mark positions to latest close.
4. Compute summary metrics.

### 4.3 Refactor Phase

- Keep simulation assumptions documented in README.

## 5. Edge Cases

- No trades returns zero win rate and Sharpe.
- Flat equity returns zero Sharpe.

## 6. Review Checklist

- [x] Red: Metrics missing before implementation
- [x] Green: Tests pass
- [x] Refactor: Helper methods extracted
- [x] AC all met
- [x] Existing tests not broken
- [x] Code style followed
- [x] No unnecessary changes
