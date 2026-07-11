# T2: Quant Signal Engine

**PRD Ref**: PRD-nasdaq-auto-trader > US-2
**Priority**: P1 (High)
**Size**: L (4-8h)
**Status**: Done
**Depends On**: T1

---

## 1. Objective

Expand the strategy from a small indicator vote into a broader classical quant
signal engine.

## 2. Acceptance Criteria

- [x] AC-1: Indicators include ATR, Donchian channel, stochastic oscillator,
  rate of change, and volume average.
- [x] AC-2: Strategy combines trend, momentum, breakout, mean reversion,
  volume, and regime signals.
- [x] AC-3: Buy decisions expose `risk_per_share`.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_breakout_momentum_volatility_indicators` | Unit | New indicator formulas work | PASS |
| 2 | `test_strategy_buys_strong_mechanical_uptrend` | Unit | Strong trend produces buy | PASS |
| 3 | `test_strategy_sells_when_stop_loss_is_hit` | Unit | Stop loss exits | PASS |

### 3.2 Test File Location

- `tests/test_indicators_strategy.py`

### 3.3 Mock/Setup Required

- Synthetic OHLCV bars.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/indicators.py` | Modify | Add indicator formulas |
| `nasdaq_auto_trader/strategy.py` | Modify | Add signal scoring |
| `nasdaq_auto_trader/models.py` | Modify | Add decision risk distance |

### 4.2 Implementation Steps

1. Add dependency-free indicator functions.
2. Extend `StrategyConfig`.
3. Add buy/sell scoring and ATR/fixed risk distance.

### 4.3 Refactor Phase

- Replace broken encoded comments with readable English.

## 5. Edge Cases

- Not enough bars returns `hold`.
- Donchian breakout uses prior bars, not the current close in the channel.

## 6. Review Checklist

- [x] Red: Tests initially failed/missing for new behavior
- [x] Green: Tests pass
- [x] Refactor: Comments cleaned
- [x] AC all met
- [x] Existing tests not broken
- [x] Code style followed
- [x] No unnecessary changes
