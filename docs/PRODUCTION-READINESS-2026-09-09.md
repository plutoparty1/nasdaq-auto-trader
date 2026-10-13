# Production readiness review — 2026-09-09

Status: in progress. No live orders or live authorization have been issued by this review.

## Work plan

1. Completed: inventory source, deployed executable, scheduled tasks, runtime configuration and launch constraints.
2. Completed: initial five review lanes identified and reproduced material defects with isolated brokers/state.
3. In progress: fix confirmed defects and verify regression tests plus manual orderless scenarios.
4. Pending: build an isolated release, audit package contents and verify the executable surface.
5. Pending: document deployment readiness, remaining live gates and operator launch/stop procedure.

## Runtime hypotheses

- H1: scheduled tasks point at stale or failing deployment; distinguish with task actions, hashes and isolated executable launch.
- H2: machine resource exhaustion prevents stable startup; distinguish with committed/free virtual memory and process failures.
- H3: current live gates or account state block intended trading; distinguish using read-only configuration/strategy/authorization/account checks.

## Review lanes

Goal/order safety, code/broker runtime, security, hands-on QA, context/deployment. All pending.

## Artifact ledger

- Evidence in `docs/qa/production-2026-09-09/` is retained as the audit deliverable.
- Temporary broker/state reproductions use self-cleaning `TemporaryDirectory` directories; no production state edits.
- Future release build uses a new staging directory; previous releases remain available.

## Initial observations

- Source worktree initially clean.
- Scheduled tasks target `dist/NasdaqAutoTrader/NasdaqAutoTrader.exe`; latest prior review packaged a separate staged executable without deploying it.
- Task results observed: unattended `1`; live canary `3221225773`.
- At 21:01 KST, Windows reported FreeVirtualMemory `56156` KiB. Git Bash child process creation failed during read-only inspection.

## Confirmed findings and containment

- H1 confirmed: deployed SHA-256 `81078C6B4ED05B05B685E24CD60BFF7E00894A11E28F0D720CF2D0224CA383E1` differs from prior reviewed staged SHA-256 `A3C9D601E21289C4E00C8EA3D51626B37215386BDF605B5945BD803C7F6D2FA0`.
- H2 confirmed: Windows virtual-memory exhaustion caused shell initialization and test subprocess failures; free C: space also observed at approximately 1.2 GiB. Do not interpret resource-failed tests as passes.
- H3 confirmed: actual settings enable LIVE, unattended LIVE and automatic session authorization; existing LIVE strategy resolves. Broker GET-only inspection at 21:15 KST succeeded with positive cash/equity, zero positions and zero open orders. See `docs/qa/production-2026-09-09/read-only-readiness.json`.
- Production session contains 12 submitted claims and one uncertain claim. No production claim was cleared. Clean current holdings/open-orders alone do not identify the historical ambiguous submission.
- Both existing scheduled tasks were disabled and the old GUI received a normal close request during repair. No account orders were submitted or cancelled. Previous task states are retained in the evidence folder. LIVE restart remains blocked pending final readiness assessment.

## Fix evidence collected so far

- Ambiguous broker responses and prior-day uncertain claims: six failing regressions, then focused suite passes.
- Sell timeout restart, close crossing, refreshed trigger and cancel-ack replacement: four failing regressions, then targeted runtime suite passes.
- Authenticated HTTP redirect and malformed OAuth cache: synthetic redirect/cache failures reproduced, then loopback transport tests pass.
- Package audit: inline broker credentials, malformed config and nonexistent package directory incorrectly passed; seven failing tests before fix, all 16 new/existing packaging tests pass after fix. Prior staged package still passes content audit.
- Read-only account probe rejects every outgoing non-GET request except OAuth token issuance, and reports `submitted_order=false`.

## Current verification limits

- Full suite rerun during active edits is diagnostic only; final immutable-source run is still required.
- LSP status reports no installed Python language servers; `ruff` and `basedpyright` are absent. Do not claim clean type/lint diagnostics.
- Live start is not approved while unresolved production uncertainty or host resource failures remain.
