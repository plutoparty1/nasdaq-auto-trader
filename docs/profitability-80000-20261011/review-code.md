# Independent code review

Verdict: **PASS**. Confidence: **HIGH** for the offline calculation paths reviewed. This verdict does not establish profitability or authorize live deployment.

## Scope and evidence

Reviewed all `nasdaq_auto_trader/profitability*.py`, the profitability extension in `scripts/run_entry_policy_comparison.py`, and `tests/test_profitability*.py`. Traced their behavior through the original entry policy, technical strategy, experimental exits, execution book, cost model, and performance metrics. Reviewed the frozen experiment profile and `PROTOCOL.md`. No production code or live configuration was edited by this reviewer.

| Boundary | Source evidence | Review result |
|---|---|---|
| Initial capital | `profitability_experiment.py:86` and `:101` select the last available historical FX observation and calculate `80000 / split_fx`. | The main output's initial USD multiplied by its actual FX equals KRW 80,000 for every case. |
| C stop distance | `profitability_strategy.py:60` and `:68` use the nearer fixed/ATR initial stop for new sizing; `:81` retains the original C protective exit path. | The original A/B/C sizing floor remains in `entry_policy_experiment.py`; the new C sizing interpretation is explicit in the frozen protocol. |
| Candidate exits | `profitability_strategy.py:81` delegates candidate protection to `ExperimentalExitStrategy`; general technical sells remain inherited. `experimental_exit.py:167` checks stop, fixed take profit, then activated trailing. | Fixed 8%, fixed 10%, and entry ATR retain their prescribed bundles. No general sell suppression was introduced. |
| Integer sizing | `profitability_risk.py:47` fixes order and position quantity at 1; `:134` separately records risk-only integer quantity. | Higher risk budgets can admit additional signals but cannot increase an accepted order above one share. |
| Costs and caps | `profitability_experiment.py:40` adds expected round-trip costs; `:100` passes `risk_includes_costs=True`. `backtest_execution.py` reserves cash/fees, counts pending plus held risk, rechecks total exposure and initial stop risk at fill, and charges each execution's commission once. | Estimated planning costs are not charged again as cash expenses. Actual execution impact is embedded in prices and separately reported, without a second equity subtraction. |
| Blocker diagnosis | `profitability_risk.py:98` accumulates independent conditions; `:140` preserves the upstream conflict/duplicate/invalid-ATR reason. Engine rejection records separately cover later submission/fill failures. | First blockers and concurrent mathematical conditions are distinguishable. Portfolio risk enforcement remains an execution-book gate, explicitly identified by the ledger. |
| Time ordering | `backtest.py:116` marks holdings at the opening before fills; `:125` then incorporates closes before decisions. Candidate fill ATR comes from the previous completed signal state. `profitability_benchmarks.py:99` buys at the next observed opening. | No future daily close enters opening risk equity or the entry ATR. Daily close protection and unknown intrabar ordering remain stated modeling limits. |
| Fill assumptions | `profitability_execution.py:12` requires a positive-volume next bar and an opening price plus adverse costs within the limit. | Merely touching a buy limit intraday is insufficient. This is still a simulation assumption, not proof of actual queue execution. |
| Metrics | `profitability_metrics.py:75` derives net PnL from full ending equity; `:89` adds recorded costs only for the explicitly labeled observed-path gross metric. Complete month statistics use `monthly_rows`, not annualization. | Open losses remain in account returns, and partial months cannot enter the complete-month target denominator. |
| Identity and preservation | `profitability_config.py:19` validates the frozen profile hash and source/data hashes; `profitability_experiment.py:54` checks fixed dates and `:61` rejects nonempty outputs. | Twelve candidates and frozen dates are preserved; prior results cannot be overwritten by the runner. |

## Resolved blocking issue

The first implementation inferred submission rejection from equal signal and rejection timestamps. `ExecutionBook` also emits `end_of_data_unfilled` at the last observation, so a legitimately submitted final-date buy could be incorrectly removed from the submitted count. An unrelated final-date sell could likewise reduce the count.

The owner replaced this calculation with `count_submitted_buys` in `profitability_experiment.py`, matching accepted buy identities and excluding end-of-data expiration. The reviewer added only `tests/test_profitability_submission_counts.py` under explicit ownership. Its three cases cover the final buy, the final sell, and an actual immediate portfolio rejection. All three passed. This reporting correction does not alter trading rules or generated trade paths.

## Actual-output reconciliation

Independently read `main/summary.csv`, `main/fills.csv`, `main/equity.csv`, `main/orders.csv`, and `main/order_rejections.csv` after the correction. All **24** main profile/cost cases and **469** fill rows passed these checks:

- Initial USD × reported initial FX = KRW 80,000.
- Every simulated fill has quantity exactly 1 and a timestamp later than its signal.
- Each equity observation equals cash plus marked positions.
- Total modeled cost equals the sum of execution commissions plus recorded execution impact.
- Net PnL equals final equity minus initial cash; reported observed-path gross equals that net plus modeled costs.
- Accepted-order row counts agree with summary candidates. Main execution rejections are exclusively next-opening fill expirations, so no hidden immediate rejection changes these submission counts.

For example, main base `fixed_8_risk1`/`risk2` both return +0.454407%, while their stress results are negative. The numeric reconciliation includes open positions. These are separate simulations; the 469 rows are not pooled trades supporting statistical confidence.

After pair output completion, independently repeated the capital, quantity, timestamp, equity, cost, net/gross, and submission checks for all **72** pair cases and **1,151** fill rows (24 cases in each of train/validation/final). All passed. Also reconciled every complete-calendar-month denominator and +10% numerator against `pair/monthly.csv`. The pair rejection ledger contains 882 next-opening expirations and **18 end-of-data expirations**; the corrected submission helper handles the latter without treating them as failed submissions.

## Verification limits and blocking issues

- This reviewer executed `python -m pytest tests/test_profitability_submission_counts.py -q`: **3 passed**. Approval is based on the source trace and actual CSV reconciliation as well as that targeted regression.
- The review shell's `python -m basedpyright` was unavailable and no standalone checker was on PATH. The owner was asked to include this test file in its configured diagnostics run. This reviewer does not claim a clean local type-check result.
- The source and numeric review cover the main and pair engines/results. Final report claims and complete user-requirement coverage remain subject to the independent goal/context/QA review lanes.
- Daily close protection does not establish the real intraday worst-case fill. Dividends, actual account-specific charges, FX conversion charges, and operational expenses remain outside the measured net result as disclosed in the experiment protocol.

Open blocking code issues: **none**.

## Follow-up: complete concurrent portfolio blockers

Verdict: **PASS**, confidence **HIGH**. Read-only review of `profitability_constraint_audit.py`, its five regression cases, and both `portfolio-audit-main` / `portfolio-audit-pair` outputs. No strategy run or performance recalculation was performed by this reviewer.

- **Held and pending semantics:** `_windows` records a submitted buy until its opening fill/expiry, then retains its original planned loss until an executed sell. Immediate rejections never reserve risk. `_used` includes every opening fill before close evaluation, includes only alphabetically earlier same-close accepted orders, removes opening sells/expirations before that close's decisions, and retains end-of-data reservations until after the last evaluation. This matches `Backtester` and `ExecutionBook` event order.
- **Independent numerical ledger check:** reconstructed an alternative chronological dictionary ledger directly from saved orders, fills, and rejections, without calling the new `_windows` or `_used` helpers. Every used-risk value and hypothetical 6% blocker matched for **7,871 main rows** and **19,947 pair rows**, including their actual expiry/end-of-data paths. This demonstrates that future outcomes do not affect the risk state assigned to an earlier decision.
- **Cost-invariant proof:** the engine retains `max(signal_plan, fill_stop_risk)` at entry. Independently recomputed both quantities for all **240 main buys** and **581 pair buys** using only signal-time ATR history, the specified stop rule, recorded limit/opening prices, and the saved cost scenario. The recorded plan matched its formula, every fill occurred after the signal and within its buy limit, and fill-stop risk never exceeded that plan. The largest `fill_stop_risk - signal_plan` was −$0.0040995303473 for main and −$0.0032262967801 for pair. Therefore using the accepted planned-risk amount for held positions is justified by the actual fills, not an unsupported approximation.
- **Preserved first/all conditions:** source hash checks passed for every recorded input artifact. The enriched row count and each source timestamp, symbol, first reason, and complete original blocker string match the numerical source CSVs exactly. Hypothetical portfolio co-blocks are explicitly labeled diagnostic-only and do not replace an earlier actual blocker. There are 1,019 main and 2,316 pair rows with that additional hypothetical condition; these are not new rejected orders or additional trading outcomes.
- **ATR diagnosis:** the prefix filter in `_volatility` excludes later bars. A valid ATR with a forbidden stop distance is separated from unavailable/invalid ATR. Main has **1,056** and pair **2,832** valid-ATR distance violations; both have **zero** missing/invalid ATR rows. When no valid initial stop exists, aggregate portfolio feasibility remains unknown rather than inventing a planned loss.
- **Scope:** the audit writes only a fresh output directory and verifies source hashes again before publishing it. It does not import or invoke the strategy runner, change candidates, revise fills, or rewrite existing performance CSVs. Regression coverage includes held plus pending overlap, immediate rejection/expiry/end-of-data handling, invalid retained-risk proof, and both ATR diagnostic categories.

Maximum reconstructed actual held-plus-pending planned risk, sampled after all daily close orders, is 4.075661644538222% in main and 3.994647461753107% in pair. The audit labels this sampling rule; it does not claim continuous intraday maximum loss.

Follow-up blocking issues: **none**.
