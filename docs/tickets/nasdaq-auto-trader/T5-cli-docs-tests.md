# T5: CLI, Docs, And Tests

**PRD Ref**: PRD-nasdaq-auto-trader > US-1, US-5
**Priority**: P1 (High)
**Size**: M (2-4h)
**Status**: Done
**Depends On**: T1, T2, T3, T4

---

## 1. Objective

Make the project usable and verifiable from the command line with readable
operator documentation.

## 2. Acceptance Criteria

- [x] AC-1: README explains usage, safety gates, strategy, and limits.
- [x] AC-2: `config.example.json` exposes new strategy/risk fields.
- [x] AC-3: CLI backtest output includes risk metrics.
- [x] AC-4: Unit test suite passes.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `python -m unittest discover -s tests -v` | Unit | Full suite | PASS |
| 2 | `python -m nasdaq_auto_trader --config config.example.json show-config` | Smoke | Config loads and prints | PASS |

### 3.2 Test File Location

- `tests/`

### 3.3 Mock/Setup Required

- No credentials for local verification.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `README.md` | Modify | Operator guide |
| `config.example.json` | Modify | New defaults |
| `nasdaq_auto_trader/cli.py` | Modify | Backtest JSON metrics |
| `tests/` | Modify | Expanded coverage |

### 4.2 Implementation Steps

1. Replace broken encoded prose.
2. Add test coverage for new behavior.
3. Run local validation.

### 4.3 Refactor Phase

- Keep final docs concise and practical.

## 5. Edge Cases

- Paper/live commands require credentials and are not run during local tests.

## 6. Review Checklist

- [x] Red: Default unittest discovery gap identified
- [x] Green: Explicit `-s tests` suite passes
- [x] Refactor: README and comments cleaned
- [x] AC all met
- [x] Existing tests not broken
- [x] Code style followed
- [x] No unnecessary changes
