# Hands-on QA scenarios (frozen before execution)

2026-10-11. Scope: offline comparison CLI only. No live application/broker/GUI. Source is read only for this review. Native Windows has no tmux; captured subprocess stdout/stderr, exit codes, output inventories and hashes provide terminal evidence.

## Initial scenarios

| ID | Priority | Steps | Expected |
|---|---|---|---|
| 01 | P0 | Run CLI --help | Exit 0; profitability option visible |
| 02 | P0 | Run without required arguments | Nonzero; required options identified |
| 03 | P0 | Run frozen synthetic plumbing profile | Exit 0, 12 profiles × 3 splits × 2 costs; explicitly synthetic |
| 04 | P0 | Change risk 4% to 5% in temporary profile | Reject before summary |
| 05 | P0 | Change order quantity 1 to 2 | Reject before summary |
| 06 | P0 | Change starting KRW 80000 to 80000 USD-sized value | Reject before summary |
| 07 | P0 | Point output at sentinel file directory | Reject; byte-identical sentinel |
| 08 | P0 | Use historical bars with changed hash | Reject before summary |
| 09 | P0 | Change frozen historical boundaries | Reject before summary |
| 10 | P0 | Change frozen FX file | Reject before summary |
| 11 | P0 | Run historical main cohort CLI | Exit 0, 24 rows, exploratory label |
| 12 | P0 | Run historical action-free pair CLI | Exit 0, 72 rows, exploratory label |
| 13 | P0 | Audit generated fills | Whole shares, ≤1 share; cost charges nonzero |
| 14 | P0 | Reconcile cash/equity/net/costs independently | Totals agree with fills and public close marks |
| 15 | P0 | Recalculate monthly target denominator | Partial months excluded; monthly compounded return agrees |
| 16 | P1 | Compare base and stress fee output | Fee math and adverse spread/slippage match protocol |
| 17 | P1 | Audit cash/integer/fractional benchmarks | Cash USD flat; integer quantities; fractional labelled nonexecutible |
| 18 | P1 | Run offline regression harness | Existing and new relevant tests pass without network |

## Augmentation after risk review

| ID | Priority | Steps | Expected |
|---|---|---|---|
| 19 | P0 | USDKRW zero/negative/NaN/Inf and blank FX source | Reject before results |
| 20 | P0 | Supply 5-minute historical provenance | Reject daily signal substitution |
| 21 | P1 | Specify unverified monthly operations cost | Reject frozen protocol change |
| 22 | P1 | Audit blocker rows | First reason and all concurrent conditions distinguishable |
| 23 | P1 | Repeat same success output path | Reject and preserve all output hashes |
| 24 | P1 | Run both mutually exclusive cohort flags | argparse rejects conflict |
| 25 | P1 | Audit complete trade PnL / sale reasons / open loss | Reconcile realized and unrealized loss; no excluded loss |
| 26 | P1 | Inspect execution order timing | Signal precedes fill, next observed open, no touch-only fills |

## Runtime hypotheses

- H1: Currency scale/frozen-configuration drift could invalidate small-account results. Distinguish with 80,000 / FX checks, changed-profile rejection, actual whole-share fills.
- H2: Cost/snapshot accounting could hide loss or inflate returns. Distinguish with independent fill/fee/cash/mark reconciliation, cost stress, monthly returns.
- H3: Frozen windows/data/execution timing could permit lookahead or retuning. Distinguish with changed hashes/windows rejection and signal/open timestamp assertions.
