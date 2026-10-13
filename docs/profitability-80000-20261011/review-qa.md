# Hands-on offline QA review

Verdict: PASS. Confidence: HIGH for offline execution and reported arithmetic; no claim of independently validated profitability or live-broker execution.

The historical outputs contain 24 main-cohort rows and 72 pair-cohort rows, exactly 12 profiles for each available split and two cost assumptions. Every one of the 1,620 recorded simulated fills is exactly one share. All account cash, market value, fees, price impact, realized/open PnL, cumulative returns, monthly returns, and sale-reason totals reconcile independently from CSV data and public OHLC. Across the compared rows, main returns range from −8.023737% to +0.454407%; pair returns range from −8.671117% to +4.676492%. Every profile has zero complete months at +10%. These checks verify the calculations; they do not establish a profitable strategy.

## Execution and safety

- QA directly drove the existing `scripts/run_entry_policy_comparison.py` CLI for help, frozen synthetic plumbing, 17 invalid-input/error cases, and repeated-output preservation. Each process exit code/stdout/stderr is saved under `qa/`.
- The existing CLI completed the explicitly synthetic 72-row plumbing run. Its synthetic returns are excluded from profitability evidence.
- Historical main/pair runs were performed by the primary worker once under the frozen protocol. This reviewer read back their actual outputs and independently reconciled every historical fill and equity observation. Historical candidate evaluation was not retuned or repeated for this review.
- `python scripts/run_offline_tests.py -q` with the five profitability and six related entry modules passed 80 tests with outbound sockets disabled. Exact module selection and runtime evidence: `qa/offline-regressions.txt` (80 passed in 23.74 seconds).
- Native Windows has no `tmux`; captured CLI subprocess output and actual file read-back serve as terminal evidence. No broker process, GUI, order/cancel call, scheduler, permanent process, EXE replacement, or live setting write occurred in this review. Public research OHLC only; no personal transaction ledger was read.

## Scenarios

The prioritized scenario list was written before execution: `qa/scenarios.md`. The following records actual outcomes for every planned scenario.

| ID | Priority | Actual result | Evidence |
|---|---|---|---|
| 01 | P0 | PASS: help exits 0 and exposes profitability profile | qa/01-help.txt |
| 02 | P0 | PASS: missing required arguments and historical inputs fail | qa/02-missing-required.txt; qa/02-missing-historical.txt |
| 03 | P0 | PASS: frozen synthetic plumbing exits 0, exactly 72 rows/12 profiles | qa/03-synthetic-plumbing.txt; qa/independent-metrics.json |
| 04 | P0 | PASS: replacing 4% risk with 5% is rejected | qa/04-drift-risk.txt |
| 05 | P0 | PASS: replacing one-share cap with two is rejected | qa/05-drift-quantity.txt |
| 06 | P0 | PASS: account-currency scale profile mutation is rejected | qa/06-drift-currency.txt |
| 07 | P0 | PASS: existing result sentinel survives unchanged | qa/07-preserve-existing.txt; qa/cli-scenarios.json |
| 08 | P0 | PASS: changed historical CSV hash rejected before summary | qa/08-changed-bars.txt |
| 09 | P0 | PASS: changed historical split boundary rejected before summary | qa/09-changed-boundary.txt |
| 10 | P0 | PASS: changed FX history hash rejected before summary | qa/10-changed-fx.txt |
| 11 | P0 | PASS: actual main output, 24 profile/cost rows, exploratory label | main/manifest.json; qa/independent-accounting.json |
| 12 | P0 | PASS: actual pair output, 72 profile/cost rows, exploratory label | pair/manifest.json; qa/independent-accounting.json |
| 13 | P0 | PASS: every simulated fill exactly one share; all have specified commission and adverse execution impact | qa/independent-accounting.json |
| 14 | P0 | PASS: cash and public close marks independently reconstruct every equity point and net/gross PnL | qa/independent-accounting.json |
| 15 | P0 | PASS: full-calendar flags, monthly compounding, median/worst month and +10% counts reconcile | qa/independent-metrics.json |
| 16 | P1 | PASS: base/stress commission, minimum fee, half-spread and slippage formulas match all fills | qa/independent-accounting.json |
| 17 | P1 | PASS: cash USD return/cost zero; integer basket one-share cap; fractional basket explicitly nonexecutable | qa/independent-metrics.json |
| 18 | P1 | PASS: related old/new regressions under offline harness | qa/offline-regressions.txt |
| 19 | P0 | PASS: zero/negative/NaN/infinite FX and blank FX source rejected | qa/19-fx-*.txt; qa/19-empty-source.txt |
| 20 | P0 | PASS: 5-minute provenance cannot replace daily signals | qa/20-intraday-rejected.txt |
| 21 | P1 | PASS: setting unknown operating costs to zero rejected by frozen protocol | qa/21-operations-cost.txt |
| 22 | P1 | PASS: first blocker/concurrent blocker/signal-only blocker counts separately reconcile | qa/independent-metrics.json |
| 23 | P1 | PASS: repeating successful output path fails and preserves all generated file hashes | qa/23-repeat-output.txt |
| 24 | P1 | PASS: incompatible cohort flags rejected by argument parser | qa/24-conflicting-cohorts.txt |
| 25 | P1 | PASS: average completed-trade PnL, average win/loss and sale reasons reconcile; open PnL retained | qa/independent-accounting.json; qa/independent-metrics.json |
| 26 | P1 | PASS: each signal precedes next observed open fill; adverse buy price fits limit and volume is positive | qa/independent-accounting.json |

## Runtime hypotheses and evidence

1. Currency conversion or profile drift could create fictitious buying power. Rejected: each historical initial USD balance × its recorded FX equals 80,000 KRW; all executed quantities are one whole share; changed risk/currency/quantity profiles fail before summary generation.
2. Missing fees or open-position losses could inflate performance. Rejected: an independent replay of CSV fills reproduces every cash balance and public-price holding mark. Per-fill fees and adverse impact, net/gross bridge, realized/open PnL, monthly compounding, maximum drawdown and reason totals agree. Base/stress are both checked. Evidence: `qa/independent-accounting.json` (53,820 numeric/structural assertions) and `qa/independent-metrics.json` (4,501 assertions); zero mismatches.
3. Changed evaluation windows or fill timestamps could permit retuning/lookahead. Rejected within this daily model: changed data hashes/FX hashes/split dates and intraday substitution fail; all historical fills occur on the next observed bar at its adverse-cost-adjusted open. This does not validate intraday protective-stop behavior or actual queue fill probability.

## Finding resolved during review

The first new manifest inherited the legacy statement that all policies used 1% risk. The primary worker corrected new-run metadata to state the actual 1%/2%/4% profiles and retained original metadata. `qa/metadata-check.json` confirms valid corrected protocol checksums, preserved initial metadata, and unchanged hashes for all 30 historical CSVs. Candidate results and frozen settings were not altered. `metadata-correction.json` records the correction.

## Limits

Daily-bar simulations and synthetic plumbing are not live API fill verification. All historical data remain exploratory/already used. Commission assumptions are not confirmed account invoices. The whole-share passive basket omits unaffordable constituents; full fractional basket performance remains a reference. This review passes execution and arithmetic only and supports no live promotion.
