# Universe and historical holdout update — 2026-09-10

## Outcome

The built-in GUI learning flow now evaluates its fixed trend rule on a separate chronological period. Passing this historical screen permits a PAPER_CANDIDATE record, with both live permission and manual approval false. This is a historical screening policy for paper research, not independent statistical certification or proof of future profitability.

The bundled Nasdaq membership snapshot is updated to the complete official response dated 2026-09-09: 102 unique securities, exactly the previous membership minus EA. No empty-response symbol is silently removed by the data collector. Other recently listed constituents remain in the universe and may limit common history.

Sources: [official Nasdaq membership API](https://api.nasdaq.com/api/quote/list-type/nasdaq100), [EA suspension notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-545). Full response retained at `.omo/evidence/universe-refresh/nasdaq-api-20260909.json`; SHA-256 `f828df8d4b7afbc43e20b0d4eff3de02e40b5e9d68ecc5b3999a7c1219832979`.

## Evidence protocol

- Fixed template semantics are checked, including parsed fields and raw payload. No parameter fitting or search occurs.
- Default minimum: 306 aligned daily observations, partitioned into at least 60 development observations, 60 embargo observations, 60 feature warmup observations, and 126 evaluated observations. The last count approximates six trading months; a stricter configured duration increases it.
- Portfolio starts with cash and no positions; warmup produces no simulated fills. Signals at the warmup boundary execute at the next opening price. Warmup returns are excluded from measured holdout performance.
- Screen requires at least three completed simulated trades, positive return and Sharpe, a measured profit factor above one with a valid loss denominator, bounded drawdown and turnover, and valid transaction costs.
- Purged CV, CPCV, PBO, deflated Sharpe, and multiple-testing correction remain explicitly missing. They are not inferred from the holdout curve. Repeated historical screening is not presented as a new statistical trial with proven significance.
- Temporal scope and paper eligibility independently prevent advanced promotion recommendations, even when other producer flags are inconsistent. Existing champion/live approval guards remain unchanged.
- Current-universe historical results remain subject to survivorship/selection effects; this update does not implement point-in-time historical index membership or an automatic recurring membership updater.

Reports include actual test boundaries, counts, performance, cost assumptions, policy version, and registry rejection reasons. Cache reuse requires matching policy, protocol, model identity and saved model digest. Audit failures remain rejected and can recover on retry. Changed data or validation policy triggers re-evaluation. Existing live/manual/operating records remain preserved.

## Verification

- Red-to-green: absent portfolio boundary (5 failures), absent paper evidence gate (3 failures), absent learner/report/cache integration (3 failures), followed by passing targeted tests.
- Review found and reproduced inconsistent promotion flags, audit rejection/report mismatch and stale artifact reuse. Corrected; 11 affected integration/gate tests pass. A transaction-cost test was corrected to use costs high enough to cause a real rejection rather than assuming 20 bps must fail.
- Full suite: 918 passed, 17 failed, 95 subtests passed. The 17 failures are the same pre-existing failures previously reproduced before this work: seven Alpaca history cases, one pending-order duplicate guard case, two broker error-redaction cases, and seven canary redaction cases. No new failures.
- Final mechanical extraction of unchanged OpenPosition state: AST identical to prior definition; 36 backtest/holdout/integration tests and seven subtests pass afterward. Modules remain below 250 executable lines.
- Scoped Ruff checks pass. New evaluator passes BasedPyright. Existing modified pipeline files retain five baseline type errors involving AuditLogger/NullAuditLogger annotations and JSON dictionary variance; no suppressions added.
- Actual isolated Tk/controller/learner queue: missing day blocked, 100/306 history count displayed, 320-observation fixture registers one paper candidate, live resolution blocked, repeated data wording accurate, widget equals log file, no duplicate rendering, cancellation creates no artifacts. Final driver exited zero. Pixel-level screenshot verification unavailable.
- Five review lanes: goal, code quality, security, context and native QA pass after corrections.
- Windowed PyInstaller build succeeds. Ten embedded modified modules compare equal to compiled final source. Packaged diagnostic loads the new universe and reports no network client constructed and no submitted order.

Evidence and release receipts are under `.omo/evidence/universe-holdout-fix/`. Existing unrelated worktree changes were preserved. Isolated fixture directories are retained as QA evidence after automatic cleanup review rejected deletion; no debug instrumentation or production worker was left running.

## Release

Archive: `dist/NasdaqAutoTrader-universe-holdout-update.zip`.
Installer records archive/executable hashes in `release.json` and the verified installation outcome in `installation.json`. It backs up overwritten files, requires the application to be stopped, verifies every copied file against the archive, and checks that protected configuration and log files are unchanged. Installation does not restart trading.

Installation completed: 1,697 files verified; five protected settings/log files unchanged. Installed executable SHA-256: `1032E03CA75C620429747EFBDF005B6D7E6A59B8777EB1AF661BD69E21108AA8`. Archive SHA-256: `355E0C09495845CCCA842A302381B21DE379733E41A760145199495E18182B4D`. The installed executable's isolated diagnostic completed, loaded the Sep9 snapshot, constructed no network client, and submitted no order. The two temporary build executables were removed; the installed executable remains at the existing dist path. No trader process remained after diagnostics.

Cleanup review returned exactly `rejected: blocked by policy` for removal of self-created QA fixture directories, without a more specific reason. These directories remain; the native harness finished and no QA worker remains running.
