# Independent local context and claims review

Date: 2026-09-29. Reviewer scope: documentation truth, source references, current execution/configuration boundaries, and the offline experiment entry point. No product files were edited. No broker, GUI, executable, scheduler, approval or live session was started or changed. No raw environment file or credential-bearing configuration was printed.

## Verdict

**PASS for documentation truth and local source boundaries.** No blocking missing source reference or source-path misconception was found. The final experiment guide and `synthetic-smoke-final` artifacts are included in this review.

This is not a second full code/financial-model review and does not independently certify past test totals, historical broker fills, the executable's embedded source, or investment performance.

## Independently checked local evidence

| Claim | Local cross-check | Result |
|---|---|---|
| Saved deployment GUI stop is 3%, take profit 5%, trailing activation/drawdown 2%/1% | Allowlisted fields read from LocalAppData trading settings; `config_runtime.apply_settings_to_app_config` converts percent values to fractions | Matches the report; distinct from daily-loss and daily-minimum risk limits |
| KIS live-capable GUI configuration differs from the base dry-run file | Deployment base has `broker=kis`, `kis.paper=false`, USD, `1Day`; GUI has `live_trading=true`, `dry_run=false` | Matches; no account connectivity claim was made |
| Trader not active at audit snapshot | Independent `Get-CimInstance` name/command-match filter returned no matching trader; both named scheduled tasks returned `Disabled` | Matches; snapshot only |
| EXE is a separate deployment artifact | Independently obtained SHA256 `B34486F790BC45D0F6E73189999F197760C77DA482C20DD1A14B94D768617CEA` | Matches runtime audit; neither report nor this review asserts embedded-code equivalence |
| Legacy remains the default | `StrategyConfig.corrected_exits=False`; `TradingEngine` constructs `TechnicalStrategy`; experimental subclass imports occur in the separate experiment runner and its tests | Matches; common invalid-price validation and sell-only API dependency correction are explicitly distinguished from opt-in exit changes |
| Daily minimum policy remains implemented | `daily_buy_objective.daily_minimum_decision` converts eligible flat HOLD to BUY; `DAILY_MINIMUM_RISK_PCT=0.05`; overrides remain in `automatic_selection` and `engine_cycle` | Matches; existing GUI minimum-buy setting remains true |
| Minimum two holdings/replacement requirement was not declared satisfied or removed | Runtime audit explicitly states no corresponding implementation was found in the current general-engine path | Correctly records an unresolved requirement rather than silently redefining it |
| Quantity/execution fix affects generic CSV backtests | `cli_commands_basic._run_backtest` calls `Backtester`; `learning_runner` and `ai_quant_lab.holdout_validation` call the separate `BacktestEngine` | Matches; no claim that learning-engine performance was repaired |
| Sell decisions no longer require buy-only cash API | `EngineCycleMixin._run_rule_decision_cycle` calls `_account_for_order` only when `decision.action == "buy"`; named regression file exists | Matches stated scope; remaining submission guards are not claimed removed |
| New logs include diagnostic context, evaluation time and bar interval | `engine_cycle` result adds `exit_diagnostics`, `evaluation_timestamp`, `indicator_timeframe`; `app_format` serializes these; `exit_diagnostics` leaves position-derived quote timestamp null | Matches; observations are not called exchange timestamps |
| Filled trade evidence is missing | `fills.csv` has exactly one header line; fill audit consistently distinguishes submissions, balance observations and confirmed executions | No fabricated 20–30-trade reconstruction or return claim found; underlying historical logs were not reread in this review |
| Smoke results are behavior evidence only | Final synthetic artifact contains 120 summary rows and `manifest.assessment=SYNTHETIC_SMOKE_ONLY`; protocol excludes learned-universe/daily-minimum replay | Matches; final settings and generated bar hashes match the manifest; no historical monthly-target probability is asserted |

## References and experiment boundary

All local Markdown links in the reviewed audit reports resolve. Every explicit `.py` reference in these reports resolves to an existing repository source or test file. Named functions checked directly include `_position_guard`, `_run_rule_decision_cycle`, `_time_based_sell_decision`, `apply_settings_to_app_config`, `_buy_block_reason`, `_sell_block_reason`, `resolve_automatic_risk_limits`, `_resolve_live`, `daily_minimum_decision`, and `_run_backtest`. The audit labels implementation-era line numbers as movable; function identities remain valid.

`experiments/early_exit/settings.json`, `profiles.json`, `provenance.example.json`, and `scripts/run_exit_experiments.py` exist. The CLI requires explicit FX rate/source/as-of inputs, rejects live experiment settings, and imports the offline package surface after installing a network/subprocess-denying audit hook. The five profile names match the loader's expected candidate list. `--compare-entry-gate` adds two separately named comparisons: entry conflict gating and completed-bar general-exit gating. No caller connects these options to current live minimum-buy policy.

The final `experiment-guide.md` accurately describes CLI arguments, candidate values, integer sizing, separately initialized evaluation splits, source-level protocol write-before-evaluation order, and refusal to reuse a frozen protocol directory. The final protocol records maximum total position and per-symbol fractions of 0.50, cash buffer 0.10, portfolio planned risk 0.06 and monthly buy halt 0.10. Its output descriptions distinguish USD monthly summaries from KRW monthly results and preserve unknown operating costs. The guide labels the older `synthetic-smoke` directory as an earlier revision and `synthetic-smoke-final` as the final artifact. One nonblocking documentation portability note was sent to its owner: Python's `py_compile` command does not itself expand a wildcard under PowerShell, so its module paths should be explicit or the command labelled Bash-only.

The current reports correctly disclose that daily bars cannot establish intraday stop order, candidate comparisons omit learned-universe/minimum-buy replay, the original generic CSV engine and learning engine differ, costs are assumptions, confirmed fills/raw historical OHLC are insufficient, and no actual return improvement has been established.

## BOOMER-6 context check

1. **Correctness:** Percent/fraction/currency and submission/fill distinctions are explicit. Local source supports the principal runtime and API-path claims.
2. **Omissions:** Two-holdings/replacement requirement, missing actual fills/OHLC/fees/FX, unknown quote freshness and unverified EXE internals remain visible. None is converted into a success assertion.
3. **Minimality:** Reports do not recommend deleting the daily-minimum policy, switching live profiles, re-enabling tasks or changing live account state to complete the offline work.
4. **Architecture:** GUI/general strategy, learned selection/validation, generic CSV execution, isolated experiments and HIVE-specific monitor are identified separately.
5. **Performance:** Existing smoke table is a bounded functional matrix; its 120 rows are not presented as 120 independent market observations or predictive evidence.
6. **Security/risk:** Independent verification used local allowlisted reads only. No network research, git history, raw credential/log dumps, broker calls or deployment mutation was needed.

## Review limitations

Historical numerical log counts and old red/green test totals are attributed to their original local audit artifacts; this review did not rerun those analyses or inspect secret-bearing source logs. Source-line drift alone is not treated as a missing reference. Current process/task observations can change after the snapshot. The separate code, QA and security reviewers own implementation and execution gates.
