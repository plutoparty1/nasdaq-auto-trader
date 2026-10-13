# Independent entry-policy code review

**Verdict: PASS after two review corrections.** Reviewed on 2026-09-29. This verdict covers the offline A/B/C implementation and the consistency of its exported simulation evidence. It does not approve live activation, establish profitability, or identify hypothetical fills as actual account executions.

The reviewer read the new entry modules, CLI and entry tests, plus their shared technical strategy, risk manager, backtester, execution, cost, and performance dependencies. The reviewer changed only this document and the explicitly authorized independent QA regression. Other agents owned the production corrections. Existing unrelated dirty files were not reverted. No broker/API/GUI invocation or parameter tuning was performed by this review.

## Findings resolved before approval

### R1: 50% total exposure was checked only before submission

**Initial severity: P1, reproduced.** An already held share worth $20 and $40 cash permitted a $10 pending buy at exactly 50% total exposure. If the held share opened at $40 before the pending buy filled, the prior implementation still bought the new share, producing $50 exposure against $80 equity, or 62.5%. The 1% trade-risk check did not prevent this separate portfolio-exposure breach.

Independent reproducer: [qa/test_review_code_regression.py](qa/test_review_code_regression.py). Its first run through `python scripts/run_offline_tests.py` failed on the intended assertion because `NEW` had been filled. The correction adds optional `max_total_position_pct` to [Backtester](../../nasdaq_auto_trader/backtest.py) and [ExecutionBook](../../nasdaq_auto_trader/backtest_execution.py). Both entry comparison adapters opt into the same prespecified 0.5 limit. Default `None` preserves other callers' prior behavior.

The fill guard uses current opening marks, other pending buy reservations, actual new notional, and equity after the new entry fee. It rejects before position mutation or fill notification. The independent regression, updated only to opt into the corrected API, now passes. The owner's regressions also exercise default compatibility, current-open versus future-close marks, commissions, pending reservations, and invalid limits.

**Existing actual results are unaffected by R1.** All 276 exported fills are in HIVE, and every buy occurs while flat. Independent chronological ledger reconstruction found no concurrent holding or quantity violations. The exact maximum new-position exposure at a buy fill was only 5.946282% across all actual outputs, far below the unchanged 50% threshold. This is a data-specific conclusion, not reliance on the closing exposure alone. No result rerun or tuning is needed to establish that this added rejection cannot alter these exported paths.

### R2: daily CLI normalized ambiguous source labels before policy validation

**Initial severity: P2, source-confirmed boundary gap.** The shared CSV loader assigns UTC to naive/date-only values. Calling it before checking raw labels let an ambiguous daily date become a seemingly explicit completed timestamp. The daily CLI also did not compare source bars with recorded collection time. The collected artifacts already had explicit completed-session timestamps, so their evidence was unaffected.

[entry_comparison_inputs.py](../../nasdaq_auto_trader/entry_comparison_inputs.py) now validates original CSV timestamps for explicit time and timezone and rejects bars later than `collected_at`. [run_entry_policy_comparison.py](../../scripts/run_entry_policy_comparison.py) requires that provenance field and invokes validation before `load_bars_csv`. Regression coverage rejects date-only, naive, and not-yet-observed rows. This does not claim to infer exchange close semantics from arbitrary timestamp text: collected-source provenance remains responsible for identifying a completed daily close.

## Verified implementation contracts

| Contract | Source and runtime evidence | Result |
|---|---|---|
| Current low-score minimum-entry path and following general sell | `test_entry_policy_engine.py` constructs the real engine with an in-memory account and broker methods that fail on actual submission/cancellation. Score 0 is promoted; risk exceeds the normal 1% amount under the current minimum path; the next +5-minute cycle returns a technical sell. Separate policy regression shows identical input fingerprints and qualifying sell score. | PASS; fixture reproduction, not historical fills |
| B permits zero buys and does not manufacture holdings | B returns the base strategy decision; disabled-minimum engine regressions cover zero buys, retired flag values, and existing holdings. | PASS |
| C conflict veto and completed-bar gate | `EntryPolicyStrategy.evaluate()` and `_entry_policy()` veto a qualifying same-input sell score while flat, suppress equal/revised/older completion timestamps, and release only on a newer completion. | PASS |
| Protection remains available on repeated or unavailable general data | Protection executes before the C gate and uses a valid position mark. Incomplete/future histories are filtered before ATR; a valid mark retains fixed protection even with no completed history. Intraday tests check a new mark with the same daily snapshot. | PASS |
| Identical legacy exit parameters | A/B/C share the same frozen `StrategyConfig`: 3% fixed stop, 5% fixed profit, 2% trailing activation/1% drawdown, ATR14 x3 stop/x5 profit; `corrected_exits=False`. `initial_stop_for()` is a conservative sizing floor using the maximum distance, not a replacement exit rule. | PASS |
| Fill-only daily objective and order isolation | Session totals change only on actual fill notifications; cumulative partial quantity deltas prevent duplicate notification counting. Accepted submissions only suppress same-cycle duplicate promotion. Untouched/expired/end-of-data orders create neither holdings nor realized P&L. Full exits reset held quantity while the session fill total persists. | PASS |
| Common capital and risk constraints | Frozen profile enforces one share, $35 order maximum, 50% single/total exposure, 5% cash reserve, 1% common risk, and 2% daily new-buy halt. Protective sells bypass buy-only limits. Other pending cash reservations count toward exposure. R1 supplies the missing fill-time recheck. | PASS |
| Costs and no return double counting | Both adapters add one-share round-trip fee/adverse-execution risk allowance and set `risk_includes_costs=True`. Fill-time risk takes a maximum with the conservative stop calculation. Cash pays entry/sell fees once. Spread/slippage are embedded in fill prices; `execution_cost` is diagnostic and is not subtracted again from equity/P&L. | PASS |
| Offline separation | CLI installs network/subprocess denial before loading pure application modules through an isolated package path. Import regression verifies engine/config/KIS modules remain absent and socket/subprocess attempts fail. Product references to `EntryPolicyStrategy` are confined to offline entry modules. | PASS |
| Prior-session intraday data | `IntradayEvaluation` requires a strictly earlier market-session daily snapshot; same-session/future daily rows are excluded. Intraday labels require an explicit timezone and five-minute grid and are filtered against supplied session windows and collection cutoff. Unknown start/end semantics use the declared +5-minute availability lag. | PASS within declared provider assumptions |
| Frozen protocol and metrics | Runs refuse an existing `protocol.json`; strategy/risk/cost/split/input metadata are recorded before evaluating candidates. Fills join decision records by symbol and signal timestamp. Next-evaluation counts exclude protective reasons. Realized P&L and residual marked P&L are separate; USD and FX-translated KRW metrics retain their distinction. | PASS |
| Partial months | `complete_calendar_months` and `complete_calendar_window` use the declared split bounds; partial boundaries are excluded. Intraday monthly return/worst-month output is empty, with `insufficient_full_months`. | PASS; observed counts are not a probability |

The A proxy intentionally omits the historical minimum-entry 5% risk override and learned/dynamic candidate selection. Its fixed cohort and alphabetic processing are explicit in the protocol. A therefore compares forced promotion under matched 1% risk; it is not an exact replay of the operating policy.

## Independent runtime evidence

Initial focused run: **60 passed in 10.17s**. R1 reproducer before correction: **1 failed in 3.17s**, for the actual exposure violation. Independent reproducer plus exposure-guard suite after correction: **14 passed in 2.59s**.

Final combined command:

```text
python scripts/run_offline_tests.py -q tests/test_entry_policy_strategy.py tests/test_entry_policy_fills.py tests/test_entry_policy_engine.py tests/test_entry_intraday_replay.py tests/test_entry_comparison_metrics.py tests/test_entry_comparison_limits.py tests/test_entry_comparison_cli.py tests/test_entry_market_data_isolation.py tests/test_entry_fill_exposure.py docs/entry-policy-audit-20260929/qa/test_review_code_regression.py
80 passed in 18.89s
```

All Python test executions used the offline runner, which removes credential environment variables and denies socket connections. CLI tests run their own process with the earlier audit denial installed by the CLI. These counts describe separate runs and are not added together.

The reviewer separately read the completed CSV outputs and reconstructed each scenario's cash in chronological fill order, starting from its initial equity observation. Buy principal plus fee was deducted, sell principal minus fee was added, and per-symbol quantity was tracked. The final reconstructed cash matched `equity.csv` exactly in all scenarios. Separate fill-to-decision joins recomputed forced entries, entries below the buy threshold, simultaneous sell signals, and next-evaluation general exits. All **48 scenario rows matched**, including the literal five-minute-grid count in the intraday export.

| Export set | Scenario rows | Fills | Maximum exposure at a buy fill | Cash reconciliation error |
|---|---:|---:|---:|---:|
| [actual-main](actual-main/summary.csv) | 6 | 12 | 4.459228% | $0 |
| [actual-no-action-pair](actual-no-action-pair/summary.csv) | 18 | 226 | 5.162681% | $0 |
| [actual-spy-control](actual-spy-control/summary.csv) | 18 | 0 | 0% | $0 |
| [intraday-actual-comparison](intraday-actual-comparison/summary.csv) | 6 | 38 | 5.946282% | $0 |

For example, intraday A/base fills buy HIVE at `2026-09-23T13:40:00+00:00` from the 13:35 signal, then sells at 13:45 from the 13:40 technical signal. The exported `rsi_overbought`, `bollinger_overextension`, `momentum_negative`, and `stochastic_overbought` reasons correctly classify it as a general exit. These are simulated grid timestamps, subject to the manifest's provider-label limitation.

## Interpretation limits retained

- The short actual intraday sample has A=B: 8 completed round trips and 5 next-grid general exits under base cost. C has 2 round trips and 0 such exits. All actual intraday forced-entry fill counts are zero. This sample demonstrates a conflict/repeated-evaluation difference, not an isolated benefit from removing minimum-entry promotion.
- Main daily A/B/C are identical under base cost (2 completed round trips); stress has no executions. SPY has no executions. Zero executions must not be described as evidence of strategy quality.
- Matched-risk 1% affordability can prevent a forced proposal from becoming a fill. Decision counts must not replace fill counts.
- Five-minute bars do not establish tick-level protective behavior. Daily fills retain the declared next-bar model, and daily labels are not actual transaction timestamps. Prior-session daily snapshots differ from historical evolving daily bars.
- Calendar-month completeness here is deliberately based on calendar bounds, so boundary months starting on the first observed trading day can remain excluded. Unqualified `evaluated_months`, median, loss ratio and worst-month fields in the shared summary still include partial observation months; use the new complete-month fields for a full-month claim.
- Marked USD P&L can differ from KRW return because the FX history changes. Operational costs and actual account-specific trading fees remain unverified assumptions. Neither the fixed hindsight cohort nor the sample proves future monthly 10% attainment.
- The completed-bar ledger is in memory and is intended for isolated offline runs. It is not durable restart/reconnect order protection. Direct library callers remain responsible for truthful completed-bar identities and marks. Protocol refusal is a single-process overwrite guard, not a transactional concurrent-run lock.

## Reviewed correction snapshot

SHA-256 values sampled after the final test run:

| File | SHA-256 |
|---|---|
| `entry_policy_experiment.py` | `f283856466d42547330b7760956a8b37c71237cbaa3fbd2f98d7c5c2fe7a20af` |
| `entry_comparison.py` | `7b7e5abc42fb22bf8b8763c7399d27045ef3d914aa2d0c3d78df994139183577` |
| `entry_comparison_inputs.py` | `82096ff61d77fcfac49d9abd7cb8e1098765cd8e92a6778aefbfdcab03383f34` |
| `entry_intraday_replay.py` | `c817bb9c0b79a255fa14eaf1baf765f5c824bed64d2488aa8587bb09986e3c14` |
| `backtest.py` | `3e883dc617e24ad179621d1f184f4070f98b1687016875f0cfadcc74674175a5` |
| `backtest_execution.py` | `05fb55c20f12288f3b846d9f72e521958b6b6601c77b8ac3c5582937a5e0cec6` |
| `scripts/run_entry_policy_comparison.py` | `5044789173f99d6fcf138c799637e8ec27cfc70f19d261f6fe6b587afcca140a` |

No open blocking correctness finding remains in the reviewed offline scope.
