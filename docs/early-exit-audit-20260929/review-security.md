# Security and execution-safety review — 2026-09-29

**Verdict: PASS. No open security or execution-safety blockers in the reviewed scope.** Final isolated regression result: **60 passed in 25.26s**. This verdict covers the inspected source and isolated tests, not deployment approval or live-trading readiness.

## Resolved finding

1. **Diagnostic exception after the protective submission boundary: resolved.** The previous implementation recomputed indicator scores for a zero historical close, allowing `rate_of_change` to raise `IndicatorInputError` after `_submit_or_block_order`. The final implementation recognizes nonpositive/nonfinite close history, leaves scores unknown with `indicator_status="invalid_indicator_history"`, and catches the specific `IndicatorInputError` for score/ATR calculation. The regression `test_diagnostics_cannot_invalidate_protective_order_after_submission` now passes without a real broker. ATR diagnostics also retain the distinction between legacy zero-ATR behavior and corrected-exit behavior.

## Verified controls

| Area | Evidence | Result |
| --- | --- | --- |
| Offline CLI imports | `scripts/run_exit_experiments.py` installs its audit hook before imports and supplies an offline package namespace, bypassing the application initializer. An isolated `runpy.run_path` check found zero imported `config`, `engine`, or `brokers` module prefixes. | PASS |
| Network and child processes | Actual socket construction and subprocess launch were denied. Explicit DNS, HTTP-connect, and urllib audit events were also denied: **5/5 blocks; zero endpoints contacted**. The experiment import graph contains simulation/data/strategy code, no broker constructor or order/cancel API. | PASS |
| Mode parsing | Settings, profiles, and `run_suite` require literal `dry_run is True` and `broker == "offline_csv"`; no truthy string enables another mode. Profile `corrected` values must be booleans. | PASS |
| Input and exposure bounds | Risk fractions exclude booleans and require finite values in `(0, 1)`; starting capital is fixed at KRW 80,000. Cost inputs exclude booleans/nonfinite/negative values, commission is below 1, and combined adverse spread/slippage is below 100%. Integer orders are constrained by cash including fees, one-share/risk budget, per-position and total-exposure limits. Backtest execution revalidates quantities and prices. | PASS |
| Existing sell authorization | The buy-capacity-only correction still passes sells through `_settings_block_response` and `_submit_or_block_order`. Live-enable/confirmation, automatic authorization, market session, pending order, sell allowance and durable duplicate-signal controls remain on the normal path. Isolated guard/lifecycle tests passed. | PASS |
| File operations | Experiment code reads explicitly supplied local CSV/JSON and writes fixed report filenames under the supplied output directory. Existing frozen protocol output is rejected. No recursive deletion, arbitrary-command execution, scheduler operation, upload, publication, approval edit or runtime-setting write is present in the experiment path. | PASS |
| Diagnostic data | The new diagnostic object contains strategy values, position/price context and a strategy digest; it does not serialize application settings, environment variables, account identifiers or credentials. The pre-existing response formatter is not a newly introduced raw credential dump. | PASS |
| Artifact scan | Final safe count-only scan of **88** report/artifact files: private-key headers **0**, Bearer tokens **0**, JWT patterns **0**, secret assignment patterns **0**, account-number patterns **0**. No raw environment or credential file was printed. | PASS |

## Reproduction evidence

Command run in the repository with the offline test wrapper:

```powershell
python scripts/run_offline_tests.py -q tests/test_exit_experiment_cli.py tests/test_exit_experiment_risk.py tests/test_early_exit_engine_safety.py tests/test_early_exit_backtest_safety.py tests/test_early_exit_strategy_guards.py tests/test_early_exit_diagnostics.py tests/test_entry_capacity_exit_safety.py tests/test_auto_symbol_live_guard.py tests/test_live_authorization_lifecycle.py
```

Final observed result: **60 passed in 25.26s**, exit code **0**. The earlier diagnostic failure and the experiment worker's temporary total-exposure constructor failure are both resolved. The suite includes the actual offline CLI smoke execution, malformed settings, sizing/exposure limits, protective exits, duplicate/pending sells, live guard/lifecycle cases, and diagnostic regressions.

Isolation check: import the experiment script in a fresh interpreter without invoking `main`; assert prohibited application-module prefixes are absent; attempt socket construction and child-process launch; emit the three relevant network audit events. Output contained only `forbidden_live_module_prefixes=0; offline_blocks=5; endpoints_contacted=0`.

## Scope and limits

- Reviewed the experiment CLI/test wrapper, `exit_experiment*`, `experimental_exit*`, offline profiles, new diagnostics, and the relevant engine/formatter call sites. Existing unrelated dirty changes were not treated as this task's work or reverted.
- `run_offline_tests.py` clears known credential environment prefixes, disables pytest plugin autoload, and patches TCP connect APIs. It is a trusted regression harness, not an OS-level network sandbox; the stronger audit-hook verification applies to the experiment CLI itself.
- Pattern scans provide targeted leak detection, not a proof that arbitrary sensitive prose can never occur. Source hashing and existing files were not used to infer deployment equality.
- This reviewer did not invoke a real broker, submit/cancel an order, start a scheduler, alter live settings/holdings/approval policy, publish an artifact, or modify product code. The only owned persistent change is this review report.
