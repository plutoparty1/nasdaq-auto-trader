# T1: Research And Product Specification

**PRD Ref**: PRD-nasdaq-auto-trader > US-1, US-2
**Priority**: P1 (High)
**Size**: M (2-4h)
**Status**: Done
**Depends On**: None

---

## 1. Objective

Ground the NASDAQ auto-trading implementation in current official API docs and
classical quant references, then capture the system contract in a PRD.

## 2. Acceptance Criteria

- [x] AC-1: Alpaca order and stock-bar constraints are documented.
- [x] AC-2: Technical indicator and risk-management references are documented.
- [x] AC-3: PRD lists goals, non-goals, edge cases, and tests.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `docs_exist` | Manual | PRD and research note exist | Files present |
| 2 | `reference_links_present` | Manual | Research note includes source URLs | URLs present |

### 3.2 Test File Location

- Manual document review: `docs/prd/`, `docs/research/`

### 3.3 Mock/Setup Required

- N/A

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `docs/research/quant-reference-review.md` | Create | Source-backed research notes |
| `docs/prd/PRD-nasdaq-auto-trader.md` | Create | Product requirements |

### 4.2 Implementation Steps

1. Review official Alpaca docs and quant references.
2. Extract implementation-relevant constraints.
3. Write PRD and source notes.

### 4.3 Refactor Phase

- Keep docs concise enough to maintain.

## 5. Edge Cases

- Web references can change; links are recorded with access date in git history.

## 6. Review Checklist

- [x] Red: Missing docs identified before creation
- [x] Green: Docs created
- [x] Refactor: Source list consolidated
- [x] AC all met
- [x] Existing tests not broken
- [x] Code style followed
- [x] No unnecessary changes
