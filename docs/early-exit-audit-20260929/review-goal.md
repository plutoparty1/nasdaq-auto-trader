# Independent requirement and correctness review

Review date: 2026-09-29. Reviewer scope: the current local source, offline experiment profiles, reports and focused regression tests. This reviewer owns only this report. No product files, live settings, credentials, scheduler state, deployment files or orders were changed.

**Verdict: PASS for the authorized audit and offline comparison scope, with the explicit data and policy limitations below.** Both independently identified defects G0/G1 were corrected and rechecked. No unresolved blocker remains in this bounded requirement review. The completed experiment-guide.md was read against the final runner APIs and documented assumptions.

## Diagnostic finding resolved during review

### G1 — legacy zero-ATR protection logs the wrong effective threshold

The reviewed initial revision of `nasdaq_auto_trader/exit_diagnostics.py` dropped all nonpositive ATR values before computing thresholds, irrespective of `corrected_exits`. Because `strategy.py` intentionally retains zero-ATR behavior in legacy mode, this produced an inaccurate explanation of the operative threshold.

Independent, network-disabled reproduction: 15 daily bars with OHLC=10, one held share with average and mark=10, fixed stop 3%, fixed take profit 5%, default legacy mode. `TechnicalStrategy.protective_exit()` returns `atr_stop_loss`; the applicable legacy ATR stop is 10. `exit_diagnostics()` returns `atr_value=None`, `atr_stop_price=None`, `effective_stop_price=9.7`. A reader cannot reconcile the current sell with that threshold.

**Resolved and independently verified:** diagnostics now expose `raw_atr_value=0`, `atr_status=invalid_nonpositive_legacy_active`, `atr_stop_price=10` and `effective_stop_price=10`; validated `atr_value` remains null. Corrected mode suppresses invalid ATR thresholds, nonfinite values stay JSON-safe, and the regression pairs the actual decision with the log. The root also added narrow invalid-indicator handling so diagnostics do not fail after a protective submission. The 13-test diagnostics/engine rerun below passed. G1 is closed without a live policy change.

## Requirement map

| Requirement | Assessment and evidence |
|---|---|
| Audit current local effective settings, not source defaults | **Achieved.** Independently re-read only allowlisted fields from LocalAppData trading JSON and deployed adjacent config: stop 3%, take profit 5%, trailing activation 2%/drawdown 1%, quantity 1, KIS, 1Day, ATR14 x3/x5, live true/dry false. `config_runtime.py` maps GUI percentage units to fractions. `runtime-audit.md` distinguishes the source launcher, deployed EXE, disabled scheduler and unverified EXE/source equivalence. |
| Actual fills and recent early exits | **Limited by source data, honestly reported.** `fill-audit.md` identifies 18 submissions and nine submitted sells; the three recent score-0 daily-minimum buys followed by technical sell submissions are not called fills or realized P&L. `fills.csv` has only a header because complete fill evidence is absent. This is not a claim of zero trading. |
| A: duplicate fixed/ATR exits and ATR0 | **Achieved; G1 logging was corrected.** Legacy OR thresholds remain explicit. Corrected mode excludes invalid ATR; fixed and entry-ATR experiments select their own stop. `test_legacy_atr_stop_precedes_wider_fixed_stop`, corrected invalid-ATR tests and fixed-mode tests pass. |
| B: simultaneous buy/sell scores and repeated daily-bar evaluation | **Achieved as reproduction and isolated alternatives.** Real indicator bars reproduce flat/held/flat buy/sell/buy. Entry conflict and completed-bar general-exit gates are separately named optional candidates. The live daily-minimum HOLD-to-BUY policy is deliberately preserved and is not replayed by the technical-only comparison. |
| C: 100 -> 102 -> 100.98, gap below entry, restart and lifecycle | **Achieved within observed-price semantics.** Corrected trailing remains active below entry. Experimental state retains high water/activation/initial stop across explicit export/load and partial sells, resets on complete exit/reentry, and rejects mismatched fingerprints. No preentry bar high is imported. Actual between-poll highs cannot be reconstructed. |
| D: stop distance and quantity risk congruity | **Achieved for explicit experiments.** Legacy max(fixed, ATR) sizing remains conservative. Experimental initial stop and fill observer use the selected stop anchored to actual simulated entry; cost-inclusive risk and fill-time bounds are checked. No silent min-distance change increases live quantities. |
| E: quantity buys, extra buys, partial sells, high water, execution costs | **Achieved for generic CSV engine.** `Backtester` delegates fills to `ExecutionBook`; one-share and notional buys both work, average basis and entry fees accumulate, partial sells preserve residuals, and fees/impact are counted once. Tests exercise these observable balances. The separate learning backtester is explicitly outside the claimed fix. |
| E: limits, gaps, reservation and duplicates | **Achieved within documented model.** Signals fill only on a later bar; limit touch and better opens respect limit prices. Cash and portfolio risk are reserved across pending orders and rechecked at fills; duplicate timestamps and duplicate pending orders are rejected. GTC survival and last-bar unfilled orders are covered. Touch assumes full liquidity; broker queue/partial-fill probabilities are not modeled. |
| F: holdings protection versus new-entry dependencies | **Achieved for the confirmed buy-capacity bug; preserved policy limits disclosed.** `EngineCycleMixin._run_rule_decision_cycle()` queries `_account_for_order()` only for buys. Existing account/position, approval, pending and dedup checks remain. Automatic-selector failures, sell-count caps and automatic-session cooldown may still block protection as documented in `exit-audit.md`; no unauthorized bypass was introduced. |
| Separate current / corrected / fixed8 / fixed10 / entryATR comparisons | **Achieved.** `profiles.json` defines five prescribed candidates; the first two share audited effective thresholds while `corrected_exits` differs. Fixed8 and fixed10 also have explicit take-profit/trailing assumptions. Entry ATR is 14 daily bars x3, frozen at simulated fill, with explicit stop bounds. Every candidate uses the same corrected fill engine. |
| 80,000 KRW, 2%/4%, one-share and sized comparisons | **Achieved.** Settings require exactly 80,000 KRW; the suite crosses both sizing methods, both risk budgets and base/stress costs. Integer floor sizing skips unaffordable or over-risk one-share entries. Position/total exposure, cash buffer and portfolio-risk limits are applied. |
| Monthly loss limit should halt buys, not liquidation | **Achieved after review correction.** G0 below initially failed across a month boundary; the owner fixed it and added a regression. Protective sells remain permitted by this experiment-level monthly halt. |
| Full-account performance and costs | **Achieved for a closed simulated account.** Cash plus all marked holdings feed equity and monthly returns, including unrealized losses and residual holdings. Results include USD/KRW returns, drawdowns, round trips, holding time, wins/losses, exit reasons, commissions/impact and optional separate operations cost. Unknown operations cost remains null. No external deposits/withdrawals/dividends are synthesized. |
| FX, +10% target and overclaim prevention | **Achieved with interpretation limits.** FX inputs and source/as-of are explicit; constant FX is labeled a scenario. `target_months` counts USD return windows and partial first/last windows are disclosed; it must not be read as full-calendar KRW after-operations target frequency. Historical and future success claims are absent. Zero executions are labeled `no_executions`. |
| Historical train/validation/final and regimes | **Procedure provided; historical result unavailable.** CLI requires provenance and chronological boundaries, freezes protocol before runs, rejects existing protocol output and separates warmup from trading. It cannot independently certify point-in-time constituent data or label market regimes; these require supplied audited data/protocol. Synthetic results are plainly labeled functional evidence. |
| No live actions or credential exposure | **Achieved in this review and inspected runner.** The dedicated CLI installs an audit hook forbidding sockets/network/subprocess and bypasses the application initializer; regression verifies config/engine modules are not loaded. No broker construction, GUI/trading CLI, scheduler, cancellation or credential output was used here. |

## Review correction already resolved

**G0 — month-opening loss escaped monthly entry halt.** Initial independent probe: Jan31 equity 100 then Feb1 equity 89, configured 10% halt, returned `month_open_equity=89`, `month_halted=False`, BUY accepted. The owner now retains prior observed equity as the next month's opening base. `test_monthly_halt_includes_first_day_gap_from_prior_month_close` asserts no order and `monthly_loss_buy_halt`. The focused rerun below passed after this change. This finding is closed.

## Executed evidence

Initial complete focused pass, through the socket-disabled test harness:

```text
python scripts/run_offline_tests.py -q tests/test_early_exit_strategy_guards.py tests/test_early_exit_strategy_experiment.py tests/test_early_exit_backtest.py tests/test_early_exit_backtest_edges.py tests/test_early_exit_backtest_safety.py tests/test_early_exit_engine_safety.py tests/test_early_exit_diagnostics.py tests/test_exit_experiment_risk.py tests/test_exit_experiment_metrics.py tests/test_exit_experiment_cli.py
77 passed in 9.97s
```

Affected-surface rerun after month-boundary, exposure and input-validation changes:

```text
python scripts/run_offline_tests.py -q tests/test_exit_experiment_risk.py tests/test_exit_experiment_metrics.py tests/test_exit_experiment_cli.py
16 passed in 6.16s
```

After the diagnostic correction:

```text
python scripts/run_offline_tests.py -q tests/test_early_exit_diagnostics.py tests/test_early_exit_engine_safety.py
13 passed in 2.11s
```
These counts overlap and are not added. The CLI tests run the actual dedicated offline script in a subprocess; they verify its full 120-row base matrix and network prohibition. Independent G0/G1 probes loaded the dedicated runner under `runpy` without its `main`, thereby applying the same network prohibition and avoiding application config initialization. One initial PowerShell stdin probe failed on an injected UTF-8 BOM before imports; rerunning with BOM-free output encoding produced the documented results.

## BOOMER-6 assessment

- **Correctness:** core decision, lifecycle and accounting evidence is strong; independently identified G0/G1 are closed with regression evidence.
- **Omissions:** actual fill-level attribution, verified broker fees/FX, source-versus-EXE identity, historical performance, full live universe/daily-minimum replay and intraday sequencing remain explicitly unproven. Data absence is an accepted limit, not a fabricated pass.
- **Simplicity:** a dedicated offline runner composes the existing strategy/risk/backtest surfaces. Opt-in policy changes avoid a second live execution path.
- **Maintainability:** named policies, dataclass records, fingerprinted state and focused tests make the boundaries inspectable. Type/lint conclusions are limited to separately recorded checks; this reviewer did not claim a repository-wide clean type check.
- **Efficiency:** the focused suite completes in seconds. The prescribed small comparison is bounded; no large-universe performance claim or benchmark is offered.
- **Security:** live access was excluded from both the runner and this review, existing guards stay in place, and allowlisted config inspection emitted no credentials.

The verdict concerns the authorized audit and offline experimental readiness only. It cannot certify improved real returns, a monthly +10% probability, live deployment readiness, or successful broker execution. Independent code/QA reviews remain responsible for their additional findings and final combined acceptance.
