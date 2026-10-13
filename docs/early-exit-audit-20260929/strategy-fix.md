# Strategy guard audit and isolated exit policies

Scope: current local `TechnicalStrategy`, its guard and sizing calculations, plus new offline experimental exit state. This is a code-level reproduction, not attribution of historical fills. Actual runtime and fill attribution are reported separately. Existing live config files, GUI settings and executable were not changed by this work.

## Confirmed mechanisms

1. `nasdaq_auto_trader/strategy.py:102` `_position_guard` independently tests fixed and current-bar ATR exits. Entry $10, fixed stop 5%, ATR $0.02 x 3 creates fixed stop $9.50 and ATR stop $9.94. Mark $9.93 produces `atr_stop_loss`; widening only the fixed stop does not remove this early exit. This is an existing combined-rule design, not proof that any real sale had that trigger.
2. `strategy.py:29` `decide` permits a buy when both scores exceed thresholds. The real indicator regression uses 220 slowly rising bars and a $1 final rise: buy score 10, sell score 4. Repeating the same bars with states flat / held / flat returns buy / sell / buy. No timer or brokerage was involved.
3. `strategy.py:132` requires current price above entry for legacy trailing. Entry 100, observed high 102, price 100.98 exits; price 99 disables that branch even though high-water activation already occurred. It may still sell through another protective rule. Corrected mode keeps trailing active below entry.
4. `strategy.py:144` previously treated ATR 0 as a stop at entry; negative ATR reverses thresholds. The opt-in corrected mode ignores zero, negative and nonfinite ATR. Fixed and active trailing guards remain evaluated first.
5. `strategy.py:299` legacy sizing takes the greater fixed/ATR distance, while guards may exit at the smaller distance. This is conservative sizing but inconsistent with the actual stop. The legacy method is deliberately retained to avoid silently increasing live order sizes. Experimental policies use the effective selected stop; cost and quantity controls are supplied by the separate experiment/backtest engine.
6. Invalid zero, negative and nonfinite decision prices formerly could produce protective sells (e.g. zero hits a fixed stop, infinity hits take profit). All modes now return an `invalid_price` hold when the selected price is invalid. A valid position mark can still protect a holding when a bar close is invalid. No stale-price age can be inferred from the position model, which has no quote timestamp.

## Changed files and policy boundary

- `strategy_config.py:42`: `corrected_exits=False`; explicit opt-in preserves current live thresholds and below-entry trailing policy.
- `strategy.py`: positive finite selected-price and entry checks; opt-in invalid-ATR exclusion and latched trailing semantics. No threshold values changed.
- `experimental_exit_models.py`: validated fractional-unit `ExitPolicy`, typed state and diagnostic data. Stop modes are `fixed`, `entry_atr`, and `legacy`.
- `experimental_exit.py:28`: separate subclass, opt-in entry conflict filter and completed-bar general-exit gate. Protection always precedes general-signal gates and minimum holding time.
- `experimental_exit.py:96`: actual-fill callbacks receive resulting average entry and total position quantity. Entry ATR is taken from the signal history, initial stop is anchored to actual fill average, and subsequent ATR never changes an entry-ATR initial stop. Execution rejects missing/out-of-bounds initial stops before fill through `initial_stop_for`.
- `experimental_exit_state.py:64`: explicit JSON export/load, version and profile fingerprint checks, finite positive state values, atomic reject on malformed state. No automatic writes to live session files.
- `experimental_exit_diagnostics.py:9`: effective/initial/emergency stop, current and entry ATR, high water, trailing activation, scores, price source and profile fingerprint. Position-derived marks have unknown price timestamps rather than invented timestamps. `bar_interval` is caller-declared, not inferred from poll interval.
- `tests/test_early_exit_strategy_guards.py` and `tests/test_early_exit_strategy_experiment.py`: offline regressions.

Fixed experimental modes disable ATR stop and ATR take-profit. Entry-ATR mode uses only the locked initial ATR stop plus its explicit fixed take-profit/trailing settings. Optional emergency fixed protection uses the nearer absolute stop; diagnostics show both values and precedence. Default emergency protection is absent.

Partial sells preserve high water, activation and initial stop. Additional buys update the position average and quantity while preserving the prior absolute stop and high water; this deliberately never loosens protection and may yield a stricter stop relative to the new average. A confirmed zero remainder clears state. Reentry starts fresh and never imports preentry bar highs or an unrelated externally supplied high water. Explicit state reload is required to retain prior activation across restart; this offline policy is not wired into live holdings.

Completed-bar gating assumes callers provide completed bars. The legacy API cannot determine whether a daily bar is final or establish freshness of a position mark. Minimum general hold uses supplied bar/fill timestamps, not a live wall clock. These limits prevent claiming that a daily backtest reproduces intraday execution order.

## Reproduction, regression and manual execution evidence

Three orthogonal runtime hypotheses were tested: independent ATR threshold causes earlier protection; competing indicator scores cause same-bar churn; trailing loses activation below entry. Each was reproduced and toggled by the isolated policy option. These are confirmed code mechanisms; transaction-level causality remains subject to actual fill logs.

Failing-first guard command:
`python -m pytest tests/test_early_exit_strategy_guards.py -q`
Result before implementation: **9 failed, 2 passed**. Missing opt-in API, wrong invalid-price sells and below-entry trailing were the intended failures.

Failing-first experiment command:
`python -m pytest tests/test_early_exit_strategy_experiment.py -q --tb=short`
Result against the contract-only subclass: **12 failed, 1 passed**. Fixed mode still triggered ATR, entry-ATR sizing incorrectly returned $0.70 instead of $0.06, conflicts bought, and lifecycle methods were absent.

Final focused command:
`python -m pytest tests/test_early_exit_strategy_guards.py tests/test_early_exit_strategy_experiment.py tests/test_indicators_strategy.py -q`
Result: **43 passed in 5.15 s** (2026-09-29 local session). Includes real indicator score conflict, missing/zero/inverted/nonfinite ATR, actual-entry stop anchoring and fill bound recheck, same-bar and minimum-hold protection precedence, 100→102→100.98 and crash trailing, persistence corruption, restart, reentry, partial sell, additional buy, and explicit emergency stop risk.

Static check:
`uvx --offline ruff check nasdaq_auto_trader/experimental_exit.py nasdaq_auto_trader/experimental_exit_models.py nasdaq_auto_trader/experimental_exit_state.py nasdaq_auto_trader/experimental_exit_diagnostics.py nasdaq_auto_trader/strategy.py nasdaq_auto_trader/strategy_config.py tests/test_early_exit_strategy_guards.py tests/test_early_exit_strategy_experiment.py --select E9,F`
Result: **All checks passed**. `python -m compileall -q` on all four experimental modules passed. OMO Python no-excuse checker: **no violations in 6 new files**. LSP diagnostics was attempted; basedpyright is not installed and the tool reported a previous user refusal to install. No clean LSP result is claimed.

Manual matching-surface QA used the actual `Backtester`, actual `RiskManager`, actual `ExperimentalExitStrategy`, actual fill observer and integer quantity 1. Socket construction was replaced with a raising function during the whole run. Synthetic completed daily closes held $10, advanced to $10.80 and fell to $10.368; the trailing signal filled next bar at $10.30. Fixed artificial buy threshold 0 and sell threshold 999 isolated the exit. Commission assumption was 0.1% each way, with no spread/slippage in this fixture. Observed output:

```text
trades [('buy', 10.0, 1.0, ('below_long_regime',), 0.01), ('sell', 10.3, 1.0, ('trailing_profit_protection',), 0.0103)]
ending_value 55.279700000000005 ending_positions 0
actual_backtest_observer_surface=PASS
```

This is a behavior check only, not a market-performance claim. Price P&L +$0.30 less fees $0.0203 equals account gain $0.2797; all holdings closed. Costs, account budget, duplicate order handling and full cohort comparison are covered by the separate runner/backtest audit.

## Return path

Final review addendum: three additional failing integration regressions were reproduced and fixed. `initial_stop_for` now uses the retained effective stop for an existing position, so buying at 100 then adding at 110 cannot budget a newly invented tighter stop. An emergency stop is stored as an absolute first-fill price and survives average-basis changes, partial exits and restart. Export format v2 persists this state; v1 is rejected. The unsupported legacy-plus-emergency configuration is rejected. Focused strategy verification after these corrections: **46 passed**; independent core review later ran **73 passed** across overlapping strategy/execution/diagnostic suites. See `review-code.md` for original failing values and resolved reproductions.

No live profile was switched. Existing constructors use `TechnicalStrategy(StrategyConfig(...))` with `corrected_exits=False`. To reproduce the unchanged valid-data strategy in an offline experiment use that class and the audited configuration. To test only the two opt-in guard corrections use `dataclasses.replace(config, corrected_exits=True)`. To test wider or locked ATR exits instantiate `ExperimentalExitStrategy` explicitly, pass it as `fill_observer` to the offline backtester, and retain state export for restart testing. Removing the experimental profile selection returns to the baseline; do not copy these settings into live GUI or authorization files without separate review.
