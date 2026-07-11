# T2: Deterministic Learned Strategy Selector

**PRD Ref**: PRD-automatic-symbol-selection > US-2
**Priority**: P1 (High)
**Size**: L (4-8h)
**Status**: Done
**Depends On**: T1
**PRD AC**: AC-2.1 through AC-2.4, AC-5.2, AC-5.6

---

## 1. Objective

Resolve a mode-eligible validated StrategySpec from the external artifact root
and deterministically rank supplied candidate bars without any broker access.

## 2. Acceptance Criteria

- [ ] AC-1: Dry-run/paper choose only the highest-score eligible registry
  record using score descending, strategy ID ascending, and version ascending.
- [ ] AC-2: Live resolves only the promoted `CHAMPION` with exact ID/version,
  valid spec digest, `manual_approval=true`, and `allowed_for_live=true`.
- [ ] AC-3: Rollback/no-trade, corrupt/missing specs, non-finite scores, missing
  required features, and empty eligible sets return a blocked report.
- [ ] AC-4: Valid ranking with no entry threshold match returns `no_trade` and
  never falls back to a manual symbol.
- [ ] AC-5: Normalize universe/bar mappings and use symbol ascending as the
  secondary key for cross-sectional and final signal ranks.
- [ ] AC-6: `SelectionReport` contains stable strategy/universe identity,
  shortlist count, ranked scores/reasons, warnings, and block reasons.
- [ ] AC-7: A fresh artifact root returns `eligible_strategy_unavailable` and
  the Korean readiness message without creating or promoting a seed strategy.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_resolver_uses_mode_eligible_score_and_stable_ties` | Unit | Permute records | Same chosen spec |
| 2 | `test_live_resolver_requires_current_approved_champion_and_digest` | Unit | Vary live flags/digest | Block invalid cases |
| 3 | `test_rollback_precedes_paper_registry_candidates` | Unit | Valid candidate plus rollback | Blocked |
| 4 | `test_selector_returns_no_trade_without_manual_fallback` | Unit | Scores below threshold | `no_trade` |
| 5 | `test_equal_feature_and_signal_scores_are_permutation_stable` | Unit | Permute mappings | Same ranked symbols |
| 6 | `test_selector_blocks_missing_features_and_nonfinite_scores` | Unit | Invalid artifacts/data | Exact reasons |
| 7 | `test_empty_artifact_root_reports_korean_readiness_state` | Unit | First-run paths | Zero selected symbols |
| 8 | `test_operator_promotion_and_selector_share_default_artifact_root` | Integration | Register/promote then resolve with defaults | Exact same spec/root |
| 9 | `test_mode_eligibility_status_matrix` | Unit | Every StrategyStatus in dry/paper/live | Only documented statuses accepted |
| 10 | `test_complete_selection_report_is_permutation_stable` | Unit | Permute universe/records/bars | Identical order, scores, confidence, reasons |

### 3.2 Test File Location

- `tests/test_auto_symbol_strategy_resolver.py`
- `tests/test_auto_symbol_selector.py`
- Extend `tests/test_strategy_library.py`.

### 3.3 Mock/Setup Required

- Existing StrategySpec fixtures, temporary registry/spec/promoted files.
- Deterministic `PriceBar` fixtures with equal returns and scores.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/ai_quant_lab/artifact_paths.py` | Create | External registry/spec/promoted/audit paths |
| `nasdaq_auto_trader/ai_quant_lab/operator_models.py` | Modify | Share artifact-root resolution |
| `nasdaq_auto_trader/ai_quant_lab/operator_cli.py` | Modify | Default all operator paths from one root |
| `nasdaq_auto_trader/ai_quant_lab/operator_runtime.py` | Modify | Preserve shared root during path conversion |
| `nasdaq_auto_trader/execution/live_integration.py` | Modify | Remove divergent AI Quant default paths |
| `nasdaq_auto_trader/quant_data/symbol_selector.py` | Create | Resolver, ranked models, selection report |
| `nasdaq_auto_trader/quant_data/features.py` | Modify | Canonical symbol tie ordering |
| `nasdaq_auto_trader/strategies/strategy_library.py` | Modify | Stable final rank ordering |
| `nasdaq_auto_trader/engine_types.py` | Modify | Typed selection result contract |

### 4.2 Implementation Steps (Green Phase)

1. Add artifact paths and route every operator/live constructor through them.
2. Implement mode-specific registry resolution and rollback precedence.
3. Implement pure selector/report models around existing feature/strategy APIs.
4. Add canonical symbol normalization/tie keys and reason mapping.

### 4.3 Refactor Phase

- Keep artifact authorization separate from ranking and presentation.

## 5. Edge Cases

- PRD E3, E4, E7, E19, E22, E24.
- Duplicate registry versions, malformed promoted payload, missing QQQ bars.

## 6. Review Checklist

- [ ] Red test run failed for missing resolver/selector
- [ ] Green tests pass
- [ ] Refactor tests remain green
- [ ] No order or broker dependency in selector
- [ ] Deterministic permutation tests pass
- [ ] Full regression suite passes
