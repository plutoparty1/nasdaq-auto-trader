# Offline early-exit experiment QA

Verdict: PASS. Confidence: HIGH for the tested offline software behavior; no historical performance verdict. Scope: offline CLI/library only. All generated prices, FX rates, and outcomes are TEST ONLY, not historical evidence. No broker, live GUI, scheduler, or live settings are used.

## Scenario plan (written before CLI execution)

| ID | Priority | Steps / expected observable result |
|---|---|---|
| 01 | P0 | Run CLI help; show offline-only inputs without importing the live app. |
| 02 | P0 | Run synthetic smoke with explicit FX source/as-of; write synthetic-labelled manifest and all comparison tables. |
| 03 | P0 | Verify exactly five prescribed candidates across train/validation/final, one-share/risk sizing, 2%/4%, base/stress. |
| 04 | P0 | Reconcile starting USD cash with 80,000 KRW and specified FX; reconcile fill fees and ending equity. |
| 05 | P0 | Check base/stress cost arithmetic and integer-share affordability, including minimum fees. |
| 06 | P0 | Run dry_run=false and live broker configurations; fail closed. |
| 07 | P0 | Run without bars/provenance and without required FX inputs; reject incomplete historical experiments. |
| 08 | P0 | Run invalid split boundaries; reject overlapping/reversed/final-empty intervals. |
| 09 | P0 | Verify no early order uses future high-water values and filled-entry geometry. |
| 10 | P0 | Verify concurrent open positions share cash and total portfolio risk. |
| 11 | P0 | Verify no-trade results are unsupported, not interpreted as strategy success. |
| 12 | P1 | Check monthly return, monthly +10% incidence, worst window and regime totals against tables. |
| 13 | P1 | Verify account equity includes unrealized positions and report cost assumptions. |
| 14 | P1 | Verify monthly operations costs affect net returns; unknown costs remain explicitly unknown. |
| 15 | P1 | Verify optional entry gate produces a separately labelled comparison. |
| 16 | P1 | Reject NaN, infinity, nonpositive FX and negative operations costs. |
| 17 | P1 | Reject duplicate FX timestamps and FX series that begins after evaluation data. |
| 18 | P1 | Reject too-few bars / empty datasets with usable errors and no results presented as valid. |
| 19 | P1 | Reject a second run into an existing frozen protocol output. |
| 20 | P1 | Execute network-disabled targeted regression suite and inspect failures independently. |

## Added edge cases after scenario review

| ID | Priority | Steps / expected observable result |
|---|---|---|
| 21 | P1 | Equivalent UTC-offset FX timestamps collide after normalization and are rejected. |
| 22 | P1 | Zero executions with operations costs reports a loss and retains unsupported-evidence status. |
| 23 | P1 | A losing month triggers the loss stop using chronological marked account equity, then resets in a new month. |
| 24 | P1 | Cross-month open positions contribute to monthly returns and preserve arithmetic consistency. |
| 25 | P1 | One-share entry that cannot fit cash/risk/position caps records an explicit skip or rejection. |
| 26 | P1 | Empty/whitespace FX source is rejected or flagged instead of asserting provenance. |

## Execution evidence

Final execution on 2026-09-29: **115 passing test executions**, comprising 27 independently authored CLI boundary checks, 5 independent artifact/library checks, and 83 targeted repository regressions. The final manual CLI run exited 0 and printed `SYNTHETIC_SMOKE_ONLY`. All 26 planned scenario groups completed: P0 11/11 PASS; P1 15/15 PASS; P2 none.

### Reproducible commands

```text
python scripts/run_exit_experiments.py --help
python scripts/run_exit_experiments.py --synthetic-smoke --output docs/early-exit-audit-20260929/qa-review/smoke-final --usdkrw 1400 --fx-source "TEST ONLY final fixed FX assumption" --fx-as-of 2020-01-01 --compare-entry-gate
python scripts/run_offline_tests.py -q docs/early-exit-audit-20260929/qa-review/test_cli_review.py --basetemp docs/early-exit-audit-20260929/qa-review/cli-fixtures-final --junitxml docs/early-exit-audit-20260929/qa-review/cli-results-final.xml
python scripts/run_offline_tests.py -q docs/early-exit-audit-20260929/qa-review/test_artifact_review.py --junitxml docs/early-exit-audit-20260929/qa-review/artifact-results-final.xml
python scripts/run_offline_tests.py -q tests/test_exit_experiment_risk.py tests/test_exit_experiment_metrics.py tests/test_exit_experiment_cli.py tests/test_early_exit_backtest.py tests/test_early_exit_backtest_edges.py tests/test_early_exit_backtest_safety.py tests/test_backtest_holdout_boundary.py tests/test_early_exit_strategy_experiment.py tests/test_early_exit_strategy_guards.py --junitxml docs/early-exit-audit-20260929/qa-review/regression-results-final.xml
```

A completed output intentionally cannot be reused: use a fresh output directory for a new manual smoke. The QA tests use isolated temporary output directories; the immutable-output check deliberately targets the retained initial smoke artifact.

### Scenario results

| ID | Result | Actual behavior / evidence |
|---|---|---|
| 01 | PASS | Help exits 0, identifies OFFLINE ONLY and all mandatory FX arguments. Socket creation is denied; engine/config modules are not imported by the CLI isolation test. |
| 02 | PASS | Fresh `smoke-final` exits 0, manifest assessment `SYNTHETIC_SMOKE_ONLY`, seven CSV tables plus protocol/manifest/bars emitted. |
| 03 | PASS | Exactly 168 unique combinations: five prescribed candidates plus two separately named optional variants, three splits, two sizing modes, two risk budgets and two cost scenarios. Default CLI regression confirms 120 rows without optional variants. |
| 04 | PASS | For each comparison, cash independently reconstructs from 80,000/1,400 USD plus sell proceeds minus purchases and all fees; final equity equals cash plus marked holdings. |
| 05 | PASS | All 1,460 exported fills have positive integer quantities and exact `max(minimum fee, notional * commission rate)` fees. Separate backtest regressions verify adverse prices, both commission sides, minimum fees and unaffordable-share rejection. |
| 06 | PASS | `dry_run=false`, string `"true"`, `broker=kis`, 79,999 KRW and percentage-unit mistakes exit nonzero without a successful manifest. |
| 07 | PASS | Historical mode without required inputs exits nonzero. Omitting explicit FX rate/source/as-of exits argparse code 2 and names all three required arguments. |
| 08 | PASS | Reversed/outside split boundaries fail. Every exported signal/fill and equity observation falls within its frozen evaluation interval, with fills strictly later than signals. |
| 09 | PASS | Regression checks verify pre-entry price spikes never enter holding high water, future close gains cannot fund an earlier fill, and the observer receives actual filled price/quantity. |
| 10 | PASS | Regressions verify pending cash reservations, aggregate portfolio-risk caps, gap rejection rather than stealing reserved cash, and existing/reserved total exposure. |
| 11 | PASS | All 120 flat-price/FX fixture comparisons report `no_executions`; smoke retains 22 no-execution combinations instead of fabricating performance. |
| 12 | PASS | Independent calculation reconciles every monthly return, median, +10% count, loss-month fraction and worst month. Historical market-regime conclusions are unavailable and are not claimed. |
| 13 | PASS | Account arithmetic includes open holdings; 100 smoke combinations finish with nonzero position value, all reconciled against equity.csv. |
| 14 | PASS | Unspecified operations costs stay blank; explicit 1,000 KRW monthly costs reduce after-operations return. FX-only changes remain distinct from USD stock returns. |
| 15 | PASS | Optional entry-conflict and completed-bar variants have separate `SEPARATE_...` names; they do not replace any of the five exit candidates. |
| 16 | PASS | Zero/negative/NaN/infinite FX and negative/NaN/infinite operations costs fail before a successful manifest. Invalid date also fails. |
| 17 | PASS | Duplicate, empty, zero-valued or too-late FX history fails before a successful manifest. |
| 18 | PASS | Empty CSV is rejected with `CSV must contain at least one bar`; nine timestamps are rejected with the minimum-ten-timestamps message. |
| 19 | PASS | Reusing a completed output exits nonzero with the frozen-protocol warning; protocol bytes remain identical. Independently recomputed SHA-256 matches each reviewed protocol. |
| 20 | PASS | Final network-disabled targeted regression suite: 83 passed, no failures. |
| 21 | PASS | UTC-equivalent FX timestamps with +00:00 and +09:00 offsets are normalized and rejected as duplicate. |
| 22 | PASS | No-trade runs preserve unsupported-evidence status while explicit operations costs reduce return. The separate FX effect is retained. |
| 23 | PASS | A drop from previous month-end equity 100 to first-day equity 89 blocks new buying under the 10% monthly stop; a later month resets the halt. |
| 24 | PASS | Open-position monthly example returns +10% then -18.181818% and cumulative -10%; CLI monthly arithmetic independently agrees across all comparisons. |
| 25 | PASS | 1,056 smoke skips explicitly record `one_share_exceeds_risk_budget`; each planned one-share loss exceeds the recorded budget. Unit scenarios separately cover cash/position limits and minimum-fee affordability. |
| 26 | PASS after fix | Whitespace-only FX provenance initially succeeded. The implementation owner added validation; the final actual-CLI probe now fails without reporting success. |

### Evidence artifacts

- [Final CLI results: 27 passed](qa-review/cli-results-final.xml)
- [Independent arithmetic/library results: 5 passed](qa-review/artifact-results-final.xml)
- [Repository regressions: 83 passed](qa-review/regression-results-final.xml)
- [All CLI invocations and observed stdout/stderr](qa-review/cli-observations.txt)
- [Final synthetic manifest](qa-review/smoke-final/manifest.json), [frozen protocol](qa-review/smoke-final/protocol.json), [summary](qa-review/smoke-final/summary.csv), [equity](qa-review/smoke-final/equity.csv), [fills](qa-review/smoke-final/fills.csv)
- [Final artifact counts](qa-review/smoke-observations-final.json): 168 comparisons, 1,460 fills, 16,800 equity marks, 1,056 entry skips.
- [Reviewed source SHA-256 hashes](qa-review/reviewed-source-hashes.json)
- [Independent CLI checks](qa-review/test_cli_review.py), [independent artifact/library checks](qa-review/test_artifact_review.py)

### Findings resolved during review

1. **FX provenance bypass:** actual CLI accepted `--fx-source "   "`, exited 0 and emitted an empty-provenance manifest. This was reported immediately to the parent and implementation owner. The final probe passes after the owner's correction. Initial evidence remains in [the initial CLI test results](qa-review/cli-results-initial.xml) and the append-only command observations.
2. The initial repository run found five malformed-settings cases accepted: boolean/500% commission, zero SMA period, 500% stop percentage and string boolean. These tests were being developed concurrently. The final run passes all five after the owner's validation changes.
3. One intermediate run observed a new daily-interval validation test before its function had landed. The stable final run passes the daily-labelled intraday-data rejection test.
4. The initial independent empty-CSV assertion expected the ten-timestamp message too narrowly. The product correctly rejected empty data earlier in the CSV loader. The test was corrected to require the appropriate nonempty-CSV message and still requires nonzero exit/no manifest; this was not a product defect.

### Boundaries of this PASS

This review verifies offline behavior and accounting, not strategy profitability. The data and FX values are deliberately synthetic TEST ONLY fixtures, including generated weekend timestamps. No historical order replay, true rising/falling/sideways market comparison, broker-exact fee audit, market FX verification, or future monthly +10% probability is established. No live app, GUI, scheduler, broker, or network order was used. The protocol records prespecified candidates before evaluation, and the runner performs no policy search or final-window retuning; a later human-directed experiment would require a new protocol and would not preserve an untouched final holdout.

Blocking issues remaining: **none within the reviewed offline scope**.

