# T9: EXE Packaging and End-to-End Verification

**PRD Ref**: PRD-automatic-symbol-selection > US-5, Rollout
**Priority**: P1 (High)
**Size**: M (2-4h)
**Status**: Done
**Depends On**: T1 through T8
**PRD AC**: AC-5.5, AC-5.6

---

## 1. Objective

Bundle the default universe into the Windows EXE, prove private runtime data is
excluded, and drive the frozen application through deterministic diagnostics
and bounded manual GUI dry-run QA.

## 2. Acceptance Criteria

- [x] AC-1: PyInstaller spec and PowerShell build include the default universe
  through the same resource contract.
- [x] AC-2: A read-only `--diagnostic-output PATH` frozen-process surface loads
  the bundled snapshot and external artifact/state roots, writes sanitized
  readiness JSON, submits nothing, and exits with a deterministic code.
- [x] AC-3: Built `dist` contains no `.env`, `.kis_token.json`, registry,
  promoted strategy, StrategySpec, cache, session state, or audit log.
- [x] AC-4: Diagnostic execution works with no source tree and an empty
  temporary application-data profile, with bounded timeout/termination.
- [x] AC-5: Packaged GUI launches and is manually driven through first-run
  readiness plus a dry-run automatic cycle using offline dry-run data.
- [x] AC-6: Full tests/static checks available in the repo, clean EXE build,
  launch smoke, diagnostic result, and artifact inspection pass.
- [x] AC-7: `--diagnostic-fixture-root PATH` is accepted only with the read-only
  diagnostic surface, loads an external eligible paper registry/spec plus fixed
  offline bars, never constructs network/broker clients, and can produce a
  deterministic `selected` report from the frozen EXE.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
| --- | --- | --- | --- | --- |
| 1 | `test_pyinstaller_spec_and_script_bundle_default_universe` | Unit | Inspect both build paths | Same data resource |
| 2 | `test_frozen_diagnostic_has_exit_contract_and_zero_order_dependencies` | Integration | Run diagnostic handler | Sanitized readiness, no broker |
| 3 | `test_frozen_resource_smoke_without_source_tree` | Integration | Simulate frozen resources | Snapshot loads |
| 4 | `test_build_output_excludes_private_runtime_artifacts` | Integration | Recursively inspect `dist` | No private files |
| 5 | `test_packaged_diagnostic_uses_external_empty_artifact_root` | E2E | Launch EXE with temp profile/output | Readiness JSON, exit 0 |
| 6 | `test_packaged_diagnostic_selects_from_external_paper_fixture_offline` | E2E | Eligible spec and bars fixture | `selected`, all network/order spies absent |
| 7 | `test_existing_gui_launcher_contract_stays_green` | Regression | Launch/close source app | No startup exception |
| 8 | `test_diagnostic_fixture_root_rejects_wrong_surface_and_live_artifacts` | E2E | Fixture alone, GUI combination, live artifact matrix | Nonzero exit; client/order/state writes zero |

### 3.2 Test File Location

- `tests/test_auto_symbol_packaging.py`
- Extend `tests/test_gui_launcher.py`.
- Manual evidence in `docs/IMPLEMENTATION-REPORT-nasdaq-auto-trader.md`.

### 3.3 Mock/Setup Required

- PyInstaller and temporary application-data profile.
- Copy the complete PyInstaller onedir package into a temporary working
  directory, clear `PYTHONPATH`, set a temporary application-data profile, and
  use output-file polling with bounded timeout/forced termination and
  deterministic success/failure codes.
- External diagnostic fixture contains only paper registry/spec and fixed bars;
  diagnostic mode rejects live artifacts and never constructs transport/broker
  clients, providing the network-blocked QA boundary.
- GUI window verification is manual QA; automated tests use diagnostic and
  presenter/controller contracts instead of fake-process injection.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
| --- | --- | --- |
| `NasdaqAutoTrader.spec` | Modify | Bundle default universe resource |
| `scripts/build_gui_exe.ps1` | Modify | Add data and private-artifact audit |
| `nasdaq_auto_trader/gui_launcher.py` | Modify | Read-only diagnostic dispatch |
| `nasdaq_auto_trader/quant_data/diagnostic_market_data.py` | Create | File-only diagnostic bars adapter |
| `tests/test_auto_symbol_packaging.py` | Create | Resource/diagnostic/dist contracts |
| `tests/test_gui_launcher.py` | Modify | Startup and diagnostic regression |
| `docs/IMPLEMENTATION-REPORT-nasdaq-auto-trader.md` | Modify | Verification/manual QA evidence |

### 4.2 Implementation Steps (Green Phase)

1. Add identical resource inclusion to both build entry points.
2. Add the sanitized no-order diagnostic output/exit path and external
   paper-only bars/artifact fixture adapter.
3. Add recursive private-artifact inspection and build from clean output.
4. Execute empty and selected frozen diagnostics without the source tree or
   network/broker construction.
5. Launch the EXE and manually drive readiness plus dry-run auto selection.

### 4.3 Refactor Phase

- Keep diagnostic code read-only and reuse production resource/readiness APIs.

## 5. Edge Cases

- PRD E22, E23, E26.
- Stale dist, path with spaces/non-ASCII, unwritable profile/output, timeout.

## 6. Review Checklist

- [x] Red packaging/diagnostic tests fail first
- [x] Green tests pass
- [x] Refactor tests remain green
- [x] EXE build and frozen diagnostic exit 0
- [x] GUI manually driven through first-run and dry-run surface
- [x] Dist private-artifact audit passes
