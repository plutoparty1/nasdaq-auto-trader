# Fill-time total exposure guard

Scope: the shared offline `Backtester` and `ExecutionBook`; no live engine,
settings, broker API, strategy, or policy thresholds change. Existing dirty work
is preserved. This file is the scoped investigation/evidence ledger.

## Investigation

- H1: a pending buy is checked only at submission, allowing another holding's
  later gain to take the fill above the shared 50% total exposure cap.
  Source confirms `_buy` checks cash and risk but has no total exposure check.
- H2: stale/future marks inflate the fill budget. Source refutes this:
  `Backtester.run` marks every held symbol at the current open before executing
  any pending order. Regression coverage will distinguish open and close values.
- H3: the pending order borrows another order's reserved cash. Source refutes
  this: `account(available=True)` subtracts all remaining pending cash before
  `_buy` sizes the fill. The new guard must preserve that reservation accounting.

Planned retained artifacts: the two scoped source edits and
`tests/test_entry_fill_exposure.py`. No temporary instrumentation or runtime
process is needed. Tests run through `scripts/run_offline_tests.py`, which blocks
outbound sockets and removes broker/AI credentials from the test process.

## Verification

`Backtester(max_total_position_pct=None)` preserves existing callers. The new
option accepts finite fractions in `(0, 1]` and is forwarded as a keyword-only
field on `ExecutionBook`, preserving its existing positional argument order.

Before any observer call or cash/position mutation, a buy now requires:

```
opening held value + other pending cash reservations + new fill principal
    <= (current equity - new entry commission) * max_total_position_pct
```

`account(available=True)` already subtracts other pending principal and fees,
and the currently executing order has been popped from the pending book. Thus
`account.equity - account.cash` includes the held value and other reservations
without counting the current order twice. A breach records the explicit
`total_position_limit_at_fill` rejection. The guard does not force sales when
subsequent market movements alone increase exposure.

Failing-first command:

```
python scripts/run_offline_tests.py -q tests/test_entry_fill_exposure.py
```

- Before the new API: `12 failed, 1 passed` (missing constructor option).
- After adding validation and forwarding, before the execution guard:
  `4 failed, 9 passed in 4.67s`. The primary failure was
  `assert [('AAA', 20.0), ('BBB', 30.0)] == [('AAA', 20)]`.
- With the guard: `13 passed in 2.03s`.
- Existing execution/regression suite: `60 passed, 4 subtests passed in 6.04s`:
  `test_entry_fill_exposure`, `test_early_exit_backtest`,
  `test_early_exit_backtest_edges`, `test_early_exit_backtest_safety`,
  `test_backtest_result`, `test_backtest_holdout_boundary`,
  `test_entry_policy_fills`, and `test_entry_comparison_limits`.
- Independent reviewer reran its original real-`Backtester` reproduction with
  the option enabled: independent regression plus new tests `14 passed`.
- Intraday owner verified the new option at its call site together with its
  own focused suite: `23 passed`.

Coverage includes another held share doubling before a delayed limit fill,
unchanged uncapped behavior, current-open versus future-close marking, exact
commission-adjusted cap boundary, other pending reservations, rejection before
observer calls, cash preservation, and invalid finite/unit-range inputs.

An additional direct Python driver called the public `Backtester.run` surface
with the same three-bar data and toggled only `max_total_position_pct`:

```
uncapped [('AAA', 20.0), ('BBB', 30.0)] EquityPoint(timestamp='T002', equity=120.0, cash=50.0, positions_value=70.0)
capped [('AAA', 20.0)] EquityPoint(timestamp='T002', equity=120.0, cash=80.0, positions_value=40.0) [('BBB', 'total_position_limit_at_fill')]
```

`ruff check`, `ruff format --check`, and scoped `git diff --check` pass.
`basedpyright --pythonpath C:/Python314/python.exe` reports `0 errors, 19 warnings`:
10 existing production warnings (unannotated attributes and unused `pop`
returns) and 9 test-fixture warnings (unused protocol arguments and expected
raising-constructor result). Its exit status is 1 because warnings are enabled.
The skill audit reports 6 existing findings: 5 bare `ValueError` instances and
the intentionally mutable execution-book dataclass. No unrelated style migration
was made; the new cap attribute is explicitly annotated.

No temporary source instrumentation or background processes were created. The
retained artifacts are exactly the scoped fix, regression file, and this ledger.
