# Independent early-exit code review

Review date: 2026-09-29. Final verdict: **PASS — all three independently reproduced blockers resolved and reverified**. Initial review was FAIL; the evidence and resolutions are retained below. This review covers the strategy, experimental state/guard/diagnostic modules, generic backtest execution/cost modules, rule-cycle diagnostics and the new early-exit tests. Existing unrelated dirty changes were not attributed to this work. Only this report was edited by the reviewer.

`strategy-fix.md` and `backtest-fix.md` were read as implementation claims; the local source and observed executions are the authority. No broker, network, live configuration, scheduler, executable or account was used or changed. Reproductions ran in a short-lived Python process with `socket.socket.connect`, `connect_ex` and `socket.create_connection` replaced by a raising function. The diagnostic reproduction used the existing dry-run fake-broker fixture with a temporary artifact directory, removed when its context exited.

## Findings resolved during review

### R1 — P1: diagnostic scoring can raise after a protective submission

Locations at first review: `engine_cycle.py:238`; `exit_diagnostics.py:70–73`.

The result dictionary calls `exit_diagnostics` after `_submit_or_block_order` and order recording. Diagnostics recompute both general scores even when the hard-stop decision correctly avoided those calculations. The input check accepts finite zero historical closes, but `rate_of_change` rejects a zero lookback close. Consequently a valid protective order can reach its submission boundary and then lose its successful cycle result to an observability exception.

Reproduction: construct the existing `protected_engine` dry-run fixture; use 40 HELD bars at 94, replace `bars[-11]` with an OHLC zero bar, and provide the held position `qty=1, market_value=94, avg_entry_price=100`. Call the real `_run_rule_decision_cycle`, wrapping its real `_submit_or_block_order` only to count calls.

Observed output:

```text
H1_exception IndicatorInputError rate of change is undefined when prior value is zero
H1_submission_boundary_calls 1
H1_submission_side sell
H1_control ['fixed_stop_loss'] dry_run
```

The control replaces the single old zero bar with 94. This isolates diagnostic scoring as the cause; neither a live order nor a network request occurred. Moving this calculation earlier alone is insufficient if its failure then prevents the protective order. Diagnostics must preserve independently valid protection and the execution outcome, with unavailable score fields for invalid indicator input. Add the engine-level regression, not only a diagnostic serializer unit test.

**Resolution verified:** diagnostics now reject nonpositive/nonfinite score history and catch the specific `IndicatorInputError` from optional score/ATR computation. Unavailable fields have explicit status labels. The real-engine `test_diagnostics_cannot_invalidate_protective_order_after_submission` preserves exactly one submission boundary call and the hard-stop dry-run result. Independent diagnostics/engine run: **13 passed in 2.11s**. Legacy zero ATR is now reported as a raw zero with `invalid_nonpositive_legacy_active`, matching the preserved legacy stop at entry rather than displaying an unrelated wider effective stop.

### R2 — P2: additional-fill risk checks use a different stop from the retained position state

Locations at first review: `experimental_exit.py:89–104`; `backtest_execution.py:150–160,178`.

`initial_stop_for` computes a fresh stop from the additional fill price. `register_entry_fill` subsequently retains the original absolute stop. The executor budgets the fresh, nearer stop and adds that estimate to held risk, while the resulting holding is protected at the older, lower stop. Both per-trade and aggregate limits can pass despite larger actual planned loss.

Reproduction: the real `Backtester`, existing scripted buy decisions on bars 0 and 1, integer one-share `MarketOrders`, and an actual fixed-policy `ExperimentalExitStrategy` as fill observer. Start at $1,000, set per-trade risk to 1.2% and portfolio risk to 2%. Bars are: 100; open 100 / close 110; open 110 / close 110. The first fill anchors the 8% stop at 92; the second fill is 110. No fees or spread are needed to expose the issue.

Observed output:

```text
H2_fills [(100.0, 1), (110.0, 1)]
H2_avg_qty_stop 105.0 2.0 92.0
H2_actual_basis_to_stop_loss 26.0
H2_portfolio_cap_at_fill 20.2
H2_second_fill_loss_to_retained_stop 18.0 trade_cap 12.120000000000001
H2_rejections []
```

The experiment comparison risk adapter currently disables additional buys, which bounds this defect's effect on that specific runner. The generic executor and observer explicitly support additional fills, so their risk/state contract remains incorrect. Preflight must use the effective stop that the filled state will actually retain, including emergency-stop semantics. Existing tests separately verify callback totals and stop retention; neither composes them with a real observer and risk caps.

**Resolution verified:** held-position preflight now returns `retained_stop(previous)`, the same absolute stop the fixed/entry-ATR guard uses. Emergency protection is anchored on the first fill and retained through additional buys and partial exits; schema version 2 persists that price. Existing schema version 1 is rejected rather than silently reinterpreted. The new actual-backtester regressions cover both the risk cap and averagedown/partial/restart emergency behavior. Independently rerunning the original reproduction now produces only `[(100.0, 1)]`, retained stop `92.0`, and `['portfolio_risk_limit_at_fill']`.

### R3 — P2: legacy experimental emergency protection is advertised and sized but never executed

Locations at first review: `experimental_exit.py:89–94,122–126,149–150`; `experimental_exit_diagnostics.py` effective-stop calculation.

The validated policy accepts `stop_mode='legacy', emergency_stop_pct=.01`. Entry sizing and diagnostics apply the 1% emergency stop, but `_position_guard` immediately delegates to the base legacy guard before checking it. Thus sizing assumes protection that cannot trigger.

Reproduction: existing `BothSignals` fixture, `StrategyConfig(sell_score=99)`, 15 bars at price 100 with high/low spread .5 (ATR 1), a fill at 100, then position mark 98.5. Toggle only stop mode between legacy and fixed.

```text
H3_emergency legacy risk 1.0 effective_stop 99.0 action hold reasons ['sell_fixture']
H3_emergency fixed risk 1.0 effective_stop 99.0 action sell reasons ['emergency_fixed_stop_loss']
```

Either reject legacy-plus-emergency as unsupported at policy construction, or honor the same effective emergency protection in execution and risk. The ordinary live strategy is unaffected; this is an offline policy consistency defect.

**Resolution verified:** policy construction rejects the unsupported combination with `ExitPolicyError('legacy policy does not support an emergency stop')`. Both an independent rerun and the new construction regression confirm this before any decision, fill or state mutation.

## Positive evidence and bounded limitations

- `StrategyConfig.corrected_exits=False` preserves valid-data legacy policy by default. The base strategy's nonfinite/nonpositive price hold is an explicit safety change; no live threshold values were switched. Experimental construction opts into corrected semantics and does not construct a broker.
- Entry ATR is cached on a valid signal and consumed at actual fill; first fills anchor to the actual resulting average. Entry-ATR fill bounds are checked before cash or holdings mutate. A GTC pending order skips reevaluation, retaining its original entry-volatility observation.
- The stateful experimental trail remains active after price falls below entry; partial exits retain initial stop, high water and activation; confirmed full exit clears state; reentry starts fresh. State reload rejects invalid finite-number data and fingerprint mismatch without partially replacing existing state. The additional-buy risk mismatch is R2.
- Missing/zero/nonfinite ATR does not prevent earlier fixed/trailing guards. Hard protection precedes the experimental minimum-hold and completed-bar general-signal gates. Timestamp freshness and completed-bar status remain caller assertions, as documented.
- Quantity and notional buys, explicit quantity increments, next-bar execution, limit touch/better gap prices, buy cash reservations, aggregate pending risk, proportional entry-fee allocation and residual position basis are implemented and covered. Daily bars do not reproduce intrabar stop timing; final holdings remain marked rather than forcibly liquidated.
- The executor skips all strategy evaluation while a symbol has a GTC pending order. This prevents duplicate order replacement, but also means a resting sell can block fresh protective evaluation indefinitely. No cancel/replace mechanism is claimed here. Current comparison orders use day duration, so this is a documented modeling limitation rather than an additional blocker for those results.
- Diagnostics correctly leave broker mark timestamps unknown. Their JSON contains a strategy digest and allowlisted numeric context, not credentials. The postsubmission failure in R1 is resolved as described above.

## BOOMER-6

| Dimension | Result | Evidence |
|---|---|---|
| Bugs | PASS AFTER FIX | R1 postsubmission exception and R2/R3 stop/risk disagreements independently reproduced, fixed and reverified. |
| Omissions | PASS AFTER FIX | Composed regressions now cover invalid historical score input after protective execution, additional fills with the real observer under caps, averagedown/restart emergency protection and legacy plus emergency policy rejection. |
| Over-engineering | PASS | Offline policy, state, costs and execution are separated; no live deployment or unrelated refactor was added to this review. |
| Maintainability | PASS | The fixed/entry-ATR state, guard, preflight and diagnostics share retained-stop semantics; unsupported legacy emergency configuration fails at construction. |
| Efficiency | PASS WITH NOTE | Deterministic event ordering and bounded histories; live diagnostics recompute full indicator scores after the strategy, increasing work. No performance benchmark or production-latency claim is made. |
| Risks | PASS WITH LIMITS | Identified execution-result and offline risk defects are resolved. Live settings/broker boundaries remain intact. Daily-bar timing, GTC cancel/replace and broker-mark timestamp limits remain explicit. |

## Test evidence

Command independently run:

```text
python scripts/run_offline_tests.py -q tests/test_early_exit_strategy_guards.py tests/test_early_exit_strategy_experiment.py tests/test_early_exit_backtest.py tests/test_early_exit_backtest_edges.py tests/test_early_exit_backtest_safety.py tests/test_early_exit_diagnostics.py tests/test_early_exit_engine_safety.py
```

Result at the review point: **1 failed, 68 passed in 4.33s**. The parent had just added the failing-first `test_diagnostics_cannot_invalidate_protective_order_after_submission`; it failed with the same `IndicatorInputError` independently observed above. This is expected red-stage evidence, not a claim that the pre-review suite already covered the defect. The three focused reproductions above are additional evidence beyond the earlier broad green suite.

After the fixes, the reviewer reread all changed strategy/state/diagnostic contracts and independently repeated the same seven-file command: **73 passed in 3.41s**. The original R2 and R3 standalone reproductions were rerun separately and produced the corrected outcomes quoted above. There are **no remaining blockers in this review scope**. This PASS is a source/offline correctness assessment; it does not certify live deployment, real fills or investment performance.
