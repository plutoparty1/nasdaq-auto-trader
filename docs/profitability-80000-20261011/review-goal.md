# Independent goal and constraint review

Verdict: **PASS**. Confidence: **HIGH** for the fixed offline comparison and its stated conclusions. This is not approval for trading or evidence of future profitability.

## Scope and independent evidence

Read the user's full specification, `PROTOCOL.md`, the frozen offline profile, all new profitability modules, the original entry/exit policies and execution gates, the original comparison references, the legacy audit and replay identity artifact, the new main/pair result tables, and focused regression tests. No trading code or configuration was changed by this reviewer. The only owned artifact is this review.

Ran a separate, read-only standard-library reconciliation against **96 actual scenario rows**: main 24 and pair 72. These represent 12 fixed profiles repeated across cost assumptions and existing windows, not 96 tuned candidates. Verified:

- Starting USD multiplied by the reported starting FX equals KRW 80,000.
- Net PnL divided by initial cash equals cumulative account return.
- Recorded gross PnL equals net plus modeled commissions and execution impact.
- Realized plus unrealized PnL equals total account PnL, which equals final equity minus initial cash.
- Total modeled costs equal the sum of recorded fill fees and execution impact.
- Complete-month counts and target counts reconcile to the monthly files; all 96 candidate rows have zero complete months reaching +10%.
- All **1,620 simulated fill rows** use exactly one share. These are overlapping scenario simulations and are not an independent pooled sample.

The command printed `main PASS 24 rows 469 fills 2856 equity rows`, `pair PASS 72 rows 1151 fills 10920 equity rows`, and `reviewed_account_reconciliations 96`.

Compared full CSV strings after removing only profile/risk identity fields. Main base fills, equity and rejection paths are exactly equal for C risk2/risk4, fixed8 risk1/risk2, and fixed10 risk1/risk2/risk4. Their equal outcomes are not display rounding and do not represent different order sizes.

## Goal coverage in calculation artifacts

| Required behavior | Evidence and assessment |
|---|---|
| Preserve original A/B/C 1% comparison | The old files remain separate. `identity-check.json` records all 24 daily policy/cost/window replay paths matching original fills, equity, decisions, skips and rejections. The historical 5% live exception is explicitly excluded. |
| Diagnose first and concurrent constraints | Legacy replay stores the actual first reason and independent mathematical conditions. New `constraints.csv` and `blockers.csv` distinguish first blockers, all co-blockers and buy-signal co-blockers; later engine rejections remain separate. |
| Use actual small-account capital and quantity | Historical FX converts KRW 80,000 to USD, and one-share sizing combines initial stop distance and estimated round-trip costs with the retained cash/allocation/order caps. The actual maximum filled quantity remains one. |
| Separate stop distance from risk budget | Four exit bundles cross the fixed 1/2/4% budgets. New C uses its first actual initial stop for sizing and separately discloses that this differs from the original conservative ATR/fixed sizing proxy. Widening a stop cannot bypass a failed one-share risk budget. |
| Limit simultaneous planned losses | The common 6% execution-book gate counts pending and held planned risk, including costs. The experiment does not assume unused cash authorizes all per-trade budgets simultaneously. |
| Keep candidate and entry rules fixed | Exactly C, fixed8, fixed10 and entry ATR14×3 on completed daily bars are used; policy and source-profile hashes are checked. ATR outside 0.5–10% or invalid ATR cannot create an entry. C conflict/deduplication gates and generic technical exits remain. |
| Respect observation/execution timing | Signals use completed daily histories; entry is at a later admissible opening. The buy model requires positive volume and full adverse impact within the limit. Close-observed protection and next-open exit do not promise a realized stop-loss maximum. |
| Separate benchmarks | USD cash assumes zero interest. The integer budgeted basket leaves unaffordable names in cash and identifies included/missing symbols. The fully invested fractional reference is explicitly non-executable. |
| Include open positions and complete-month metrics | Equity-based account and monthly returns include open holdings. Main fixed8/fixed10 base paths include approximately −$0.23305225 open PnL. Target denominators exclude partial calendar windows under the preserved conservative definition. |
| Retain exploratory status | Both manifests identify already used data and no independent holdout. Existing train/validation/final names are not treated as fresh independent evidence. Synthetic tests are plumbing verification only. |
| Stop without forcing the target | No candidate reaches +10% in a complete month. The positive main fixed8 result disappears under stress, underperforms executable passive holding, and is not consistent across the supplemental windows. The evidence supports no adoption in this comparison. |

## Numerical interpretation checked

Main base fixed8 risk1/risk2 returns **+0.45440659%**, with 12 completed trades and 1.91071451% average exposure. Stress returns become **−1.48930684%** and **−3.69849509%**, respectively. The executable integer passive basket returns **+1.70427999%** base and **+1.51740773%** stress; USD cash is 0% before FX translation.

Main C risk1 returns −1.10939395%, C risk2/risk4 −5.30263814%; fixed8 risk4 −6.85198599%; fixed10 all budgets −1.28813967%. Main entry ATR risk1/risk2 makes no trades, while risk4 returns −5.25774264% from only two completed trades. Its loss occurs in partial months, so a zero worst *complete* month must not conceal its cumulative loss.

The pair has isolated positive windows, including fixed10 validation and ATR risk4 validation/final. It also has adverse or nontrading windows, cost sensitivity and sparse ATR evidence. These observations do not establish repeatable profitability or a reason to promote a candidate to live trading.

## BOOMER-6 structural critique

| Perspective | Review |
|---|---|
| B — Bugs and correctness | Account, cost, quantity and full-month reconciliations pass for all 96 rows. Equal execution paths were checked at full precision. The code review's submission-count issue was corrected without changing trading paths. |
| O — Omissions | Required metrics exist in summary/monthly/reasons/equity tables, including open losses, average wins/losses, costs and risk-blocked entries. The completed report includes feasibility, five direct answers and model limitations. |
| O — Over-engineering | The existing CLI, strategies, execution book and metric engine are reused. New modules are scoped to offline risk diagnostics, fixed experimental identity, conservative execution, benchmarks and reporting. No live execution integration is needed. |
| M — Maintainability | The separate profile and hash checks make the experiment reproducible and prevent silent candidate drift. Legacy identity artifacts distinguish diagnostic replay from new economic assumptions. |
| E — Efficiency | The finite 12-profile matrix and fixed two cost scenarios bound the work. No parameter search or loop toward a desired return appears in the reviewed path. The reviewed actual outputs are finite and complete. |
| R — Risks | Results are exploratory; costs, FX, corporate actions and bar-based execution have explicit limits. One-share caps and marked open positions prevent hidden leverage or exclusion of losses. No inference of live-trading approval follows from a review PASS. |

## Completed narrative and feasibility gate

Read all eight sections of `REPORT.md`, the complete metric/monthly table definitions, `feasibility.md`, the existing final-result CSVs and `reproduce.sh`. The report leads with **이번 비교에서 채택할 후보 없음**, shows all 12 main base/stress profiles and all supplementary results, answers the user's five questions directly, and preserves the distinction between the corrected C baseline and demonstrated profitability. It gives no live promotion or permanent impossibility claim.

The report explicitly names the different new C sizing proxy, common 6% aggregate ceiling and stricter fill assumptions, so the old-versus-new C difference is not attributed to a single policy change. It keeps generic technical sells active and lists the exit priority for each policy bundle. The partial-month ATR loss, remaining losing HIVE position, zero-trade ATR cases and negative stress outcomes are visible.

Feasibility is a prespecified first-evaluation diagnostic, not a newly optimized entry date. It supplies the actual price, cost-inclusive loss, minimum account capital and minimum required risk/allocation limit. For example, first-evaluation CMCSA requires 52.423945% single-name concentration at current capital, versus the unchanged 50% cap. HIVE's valid ATR implies a 20.496899% stop, outside the frozen 10% maximum; the report distinguishes this from missing data and does not permit it. Buying one share of every main-universe name requires approximately $114.293657 if the common 50% total exposure cap is preserved. No such relaxation is applied.

Reviewed the late read-only `profitability_constraint_audit.py` supplement and both portfolio-audit summaries. It reconstructs pending/held planned risk from saved orders/fills without rerunning the strategies or overwriting their outputs. It separates valid ATR outside the stop bound from missing/invalid ATR. Main/pair aggregate-risk co-blockers total 1,019/2,316 across all scenarios and diagnostic rows; actual maximum sampled used risk is 4.075662%/3.994647%, below the common 6% ceiling. Counterfactual co-blockers are not presented as additional submitted orders. Missing/invalid ATR count is zero in these actual datasets; outside-bound counts are separate.

The executable benchmark is accurately described as HIVE one share plus residual cash, with unaffordable CMCSA/KDP missing. Fractional reference gains are marked non-executable. The report describes zero USD cash interest, separate USD/KRW results, uncertain actual fees/levies/FX/operating charges, omitted dividends and their recorded-path overlap check, daily-close protection limits and no independent holdout. The reproduction script invokes only the isolated CSV CLI and separate frozen offline profile.

Open blockers: **none**. The result supports rejecting these candidates for adoption in this comparison; it does not establish a reliable return strategy or a future monthly-target probability.
