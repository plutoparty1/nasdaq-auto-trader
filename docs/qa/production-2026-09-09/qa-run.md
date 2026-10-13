# Production QA execution evidence — 2026-09-09

Owner: QA execution lane. Scope: automated baseline and isolated CLI/library scenarios; no production source edits, broker authentication, real orders, or live loops.

## Isolation and artifact journal

- Read `tests/conftest.py`: session autouse fixture redirects `LOCALAPPDATA` to pytest temporary storage.
- Read process E2E fixtures: temporary configs, synthetic credentials, environment filtering, and fake brokers.
- The Windows Tk E2E constructs a withdrawn Tk root with a fake engine and temporary state; it does not launch the live GUI.
- Baseline runner will remove trading credential environment variables and deny socket connections for the pytest process. Child CLI tests use inspected temporary configuration and environment isolation.
- Retained evidence artifacts: this report, baseline/final pytest summaries and JUnit XML, CLI scenario summaries. Temporary fixture data uses `TemporaryDirectory` and is removed on exit.
- No debug listeners, source instrumentation, persistent environment changes, or operating system tasks are created by this lane.

## Prioritized scenario plan

Each automated scenario runs its existing test module in the full suite; manual scenarios invoke the actual module entrypoint with temporary data. Expected results:

| ID | Priority | Scenario and expected result | Surface | Result |
|---|---|---|---|---|
| 01 | P0 | Dry-run once without credentials returns a QQQ decision and submits no order | CLI | Pending |
| 02 | P0 | Missing live opt-in/authorization blocks before broker submission | Existing gate tests | Pending |
| 03 | P0 | Revoked authorization is rechecked immediately before broker call | Order-time tests | Pending |
| 04 | P0 | Authorization expires at close and next session | Authorization boundaries | Pending |
| 05 | P0 | Ambiguous POST/disconnect does not repeat an order | Retry safety | Pending |
| 06 | P0 | Broker rejection/unknown response pauses unattended scheduling | Unattended tests | Pending |
| 07 | P0 | Cash, buying power, and daily limits block invalid purchases | Risk tests | Pending |
| 08 | P0 | Position caps and durable signal claims prevent duplicates | Unattended tests | Pending |
| 09 | P0 | Malformed or incomplete reconciliation fails closed | KIS reconciliation | Pending |
| 10 | P0 | All balance pages are read; repeated cursors/duplicates fail closed | KIS pagination | Pending |
| 11 | P0 | Protective exits remain active despite AI HOLD | Profit protection | Pending |
| 12 | P0 | Persisted peak state survives restarts and reaches sell path | Profit protection | Pending |
| 13 | P0 | Canary submits neither before open nor after close | Canary safety | Pending |
| 14 | P0 | Daily POST/GET attempt budgets remain bounded | Canary safety | Pending |
| 15 | P0 | Credentials are masked by process-boundary show-config | CLI | Pending |
| 16 | P1 | Root help and invalid arguments exit 0/2 with no traceback | CLI | Pending |
| 17 | P1 | UTF-8 BOM config loads successfully | CLI | Pending |
| 18 | P1 | Malformed config returns a controlled failure | CLI | Pending |
| 19 | P1 | Missing CSV returns a controlled failure | CLI | Pending |
| 20 | P1 | Diagnostic reports complete with no network client/orders | CLI diagnostic | Pending |
| 21 | P1 | Weekend, holiday, early close, DST sessions are correct | Market-hour tests | Pending |
| 22 | P1 | GUI fake-engine start/refresh errors produce operator feedback | Withdrawn Tk E2E | Pending |
| 23 | P1 | Finite numeric validation rejects NaN/Infinity | Numeric/risk tests | Pending |
| 24 | P1 | Learning never promotes live mode or sends orders | Unattended tests | Pending |
| 25 | P1 | Dry-run bounded loop exits after one run | CLI | Pending |

### Augmentation after failure-mode review

| ID | Priority | Scenario and expected result | Surface | Result |
|---|---|---|---|---|
| 26 | P0 | Audit persistence failure after accepted order stops the cycle | Order-time tests | Pending |
| 27 | P0 | Authorization reissued with same binding invalidates earlier permit | Order-time tests | Pending |
| 28 | P0 | Learned risk changes between claim and submit block the order | Order-time tests | Pending |
| 29 | P1 | Empty or corrupt persisted state fails closed | State/store tests | Pending |
| 30 | P1 | Ambiguous cancellation requires reconciliation instead of retry | KIS reconciliation | Pending |

## Runtime hypotheses

1. H1: recent order-safety paths regress under ambiguous broker responses. Distinguishing evidence: retry/canary/unattended tests observe submit counts and durable blocked state.
2. H2: runtime dependency, CLI parsing, or Windows packaging startup breaks before a safe cycle. Distinguishing evidence: full collection plus actual CLI help, config, dry-run, and diagnostic exit codes.
3. H3: state persistence, market calendar, or authorization timing permits an unsafe second action. Distinguishing evidence: storage/restart/session-boundary tests observe claims and blocked broker calls.

## Results

Execution in progress; no pass claimed yet.

- Temporary runner journaled before creation: $env:TEMP/nasdaq-qa-20260909-runner.py. Needed for Windows multiprocessing spawn; remove after final verification.
- Initial stdin harness: 801 passed, 1 harness failure, 95 subtests passed in 85.10 seconds. Multiprocessing cannot reopen the stdin filename; rerun uses an on-disk main-guarded runner.


- Manual CLI journal: TemporaryDirectory creates synthetic configs, sitecustomize socket guard, isolated app data, and diagnostic output; automatically removed. CLI children have all credential environment variables removed and PYTHONPATH restricted to the temporary guard plus source checkout. Retained qa-cli-results.json contains synthetic output only.


### Intermediate results (changes were still in flight)

- First baseline from an stdin runner: 801 passed, 1 failed, 95 subtests passed in 85.10 seconds. The sole failure was Windows multiprocessing trying to load `<stdin>`; this was a QA harness error.
- On-disk baseline runner: 818 passed, 19 failed, 95 subtests passed in 126.37 seconds. Test count grew from 802 to 837 while independent implementation workers added regressions. Failures: three active-roundtrip tests, twelve broker-transport tests, three sell-monitor tests, and one authorization multiprocessing test. The latter failed with `MemoryError` during NumPy import in spawned children.
- Eleven actual module CLI scenarios executed with temporary app data, sanitized environment, and socket-denial sitecustomize: ten passed. The one-run dry-run loop child failed before application import because the host exhausted memory (`MemoryError` in runpy/sitecustomize); this is an unresolved execution environment failure, not evidence against loop logic.
- A fresh PowerShell process independently failed with HRESULT `0x800705AF` and `The paging file is too small for this operation to complete`. This corroborates resource exhaustion across unrelated runtimes.
- All baseline output is synthetic test-fixture data. No production configuration contents or private broker responses were captured.
- Final full run and failed CLI retry are required after workers finish and memory pressure is relieved. Current QA verdict: FAIL (no production readiness approval).
