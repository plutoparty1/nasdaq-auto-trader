# T1: Universe, Resource, and Settings Foundation

**PRD Ref**: PRD-automatic-symbol-selection > US-1, US-5
**Priority**: P1 (High)
**Size**: M (2-4h)
**Status**: Done
**Depends On**: None
**PRD AC**: AC-1.1 through AC-1.4, AC-5.5, AC-5.6

---

## 1. Objective

Add a strict, versioned Nasdaq-100 universe resource and the backward-compatible
automatic-selection setting without creating a broker or selecting an order.

## 2. Acceptance Criteria

- [ ] AC-1: Parse an immutable `UniverseSnapshot` only when schema version,
  effective date, source URL, checksum, symbol format, uniqueness, and 1-120
  membership bounds are valid.
- [ ] AC-2: Bundle the source-dated June 22, 2026 snapshot with the required
  additions and removals from PRD AC-1.4.
- [ ] AC-3: Resolve the default JSON in source and frozen runtimes through a
  PyInstaller-aware resource API and fail with a typed reason when absent.
- [ ] AC-4: Persist `auto_symbol_selection_enabled=false` by default and allow
  an empty manual ticker only when that setting is true.
- [ ] AC-5: In auto mode, runtime configuration does not derive entry symbols
  from `ticker` or `ai_candidate_tickers`; manual mode remains unchanged.
- [ ] AC-6: Resolve a stable writable application-data root outside the source,
  install, and PyInstaller extraction directories.
- [ ] AC-7: Snapshot age is calculated from an injected market clock; older
  than 120 days is a typed live block and an explicit dry-run/paper warning.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_default_nasdaq_snapshot_has_june_2026_membership` | Unit | Load bundled snapshot | Additions present, removals absent |
| 2 | `test_universe_rejects_duplicate_invalid_empty_and_oversized_symbols` | Unit | Parse invalid fixtures | Typed validation reasons |
| 3 | `test_universe_rejects_checksum_and_effective_date_errors` | Unit | Tamper metadata/data | Fail closed |
| 4 | `test_resource_loader_supports_source_and_frozen_roots` | Unit | Simulate both resource modes | Same validated bytes |
| 5 | `test_settings_round_trip_auto_selection_default_false` | Unit | Load old and new JSON | Backward-compatible values |
| 6 | `test_auto_mode_accepts_empty_manual_ticker_without_candidate_fallback` | Unit | Validate/apply settings | Empty runtime entry symbols |
| 7 | `test_application_data_root_never_uses_meipass` | Unit | Simulate frozen runtime | External writable path |
| 8 | `test_snapshot_staleness_blocks_live_and_warns_nonlive` | Unit | Clock >120 days after effective date | Live block; dry/paper warning |
| 9 | `test_missing_frozen_universe_returns_typed_resource_error` | Unit | Remove frozen resource | `universe_resource_missing` |

### 3.2 Test File Location

- `tests/test_auto_symbol_universe.py`
- `tests/test_auto_symbol_settings.py`

### 3.3 Mock/Setup Required

- Temporary directories, fixed clock, patched `sys.frozen`/`sys._MEIPASS`.
- No network or broker fixture.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `nasdaq_auto_trader/quant_data/universe_snapshot.py` | Create | Typed snapshot parser and validation |
| `nasdaq_auto_trader/quant_data/resources.py` | Create | Source/frozen resource and app-data paths |
| `nasdaq_auto_trader/quant_data/defaults/nasdaq_100_universe.json` | Create | Versioned official-source snapshot |
| `nasdaq_auto_trader/config_settings.py` | Modify | Add disabled-by-default toggle |
| `nasdaq_auto_trader/config_storage.py` | Modify | Backward-compatible round trip |
| `nasdaq_auto_trader/config_validation.py` | Modify | Conditional ticker validation |
| `nasdaq_auto_trader/config_runtime.py` | Modify | Stop deriving auto entry symbols manually |

### 4.2 Implementation Steps (Green Phase)

1. Write strict immutable snapshot/resource models and failing fixtures.
2. Add and validate the default Nasdaq-100 JSON plus checksum metadata.
3. Add application-data path resolution with injectable test roots.
4. Add the settings field and conditional runtime/validation behavior.

### 4.3 Refactor Phase

- Keep path discovery separate from JSON parsing and settings mapping.

## 5. Edge Cases

- PRD E1, E2, E22, E23. Engine-level constructor/broker zero-call assertions
  for invalid, stale, and missing frozen snapshots are owned by T4 after the
  auto cycle exists.
- Frozen resource unavailable, unwritable app-data root, and old settings JSON.

## 6. Review Checklist

- [ ] Red test run failed for missing implementation
- [ ] Green tests pass
- [ ] Refactor tests remain green
- [ ] PRD AC-1.1 through AC-1.4 and AC-5.5/5.6 traced
- [ ] Full regression suite passes
- [ ] No broker construction or network calls
