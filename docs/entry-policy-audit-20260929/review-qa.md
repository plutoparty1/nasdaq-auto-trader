# Independent hands-on QA

Verdict: **PASS**, confidence **HIGH for the tested offline behavior and artifact arithmetic**. This does not approve a profitable strategy, live rollout, or faithful reconstruction of the historical executable. Reviewed 2026-09-29 in the shared workspace. Source owners fixed two defects found during QA; both original cases now pass.

The decisive evidence is the causal engine replay, the observable entry-policy changes, and the bounded real-data results. The number of passing tests is supporting evidence only.

## Actual usage and defects resolved

- Ran `python scripts/run_entry_policy_comparison.py --help`, then the actual CLI with `--synthetic-smoke --output docs/entry-policy-audit-20260929/qa/cli-smoke-final --usdkrw 1400 --fx-source "QA synthetic assumption" --fx-as-of 2020-01-01`. Exit 0, all eight CSV tables plus manifest, frozen protocol, and synthetic input produced; labeled `SYNTHETIC_SMOKE_ONLY`.
- Repeated a frozen output directory and compared the SHA-256 of every file before/after: rejected, every byte unchanged.
- Found that a nonempty directory without `protocol.json` could overwrite an existing `summary.csv`, in both daily CLI and intraday replay. Initial targeted regression output has two failures. After the owner's guard/staging fix, daily CLI, direct library, and intraday sentinel-preservation regressions pass. Evidence: [initial failures](qa/offline-tests.txt), [final run](qa/offline-tests-final.txt).
- Found that a date-only raw historical timestamp passed through the generic CSV parser as UTC midnight and produced a complete report. Runtime proof: raw `2024-12-26`, loaded `2024-12-26T00:00:00+00:00`, and the report's input hash matched the mutated file. The entry CLI now validates raw explicit timestamps and collection time first. The exact bad-data scenario now exits nonzero and creates no summary. Evidence: [runtime values](qa/timestamp-runtime.json), [original accepted fixture output](qa/cli-cases/date-only.txt), [rejected fixture](qa/cli-cases-expanded/date-only.txt).
- Ran 25 actual CLI rejection cases: frozen output reuse; zero/negative/NaN/infinite FX; negative/NaN/infinite operations cost; missing historical arguments; wrong interval; missing cohort; NaN price; negative price; invalid OHLC; date-only source timestamp; duplicate bars; short warmup; changed risk, exits, capital, policies; duplicate/late/nonfinite/malformed-date FX history. All rejected as expected. Three initial probe failures were overly specific error-message expectations; their actual rejections were already correct. [Final cases](qa/cli-cases-expanded.json).
- Ran `scripts/run_offline_tests.py` over the seven entry-policy, fills, actual-engine, intraday, metrics, limits, and CLI test modules. Final result: **54 passed in 12.17s**. Network-denial test loads the actual CLI and observes socket construction and subprocess launch rejected; broker/engine/config application modules are absent from that CLI import. The actual engine regression uses a fake broker that raises on any submit/cancel attempt.

The output-preservation evidence covers repeat invocations and existing/interrupted nonempty output directories. Concurrent competing writers were not exercised. This is an offline research CLI QA pass, not a concurrency guarantee.

## Causal behavior and unchanged protection

The actual `TradingEngine.run_once()` fake-data regression reproduced buy score **0** promoted by `daily_minimum_best_affordable`, then a general technical sell after a **five-minute** clock advance and an explicit held-position injection. The forced decision's risk distance exceeded the ordinary 1% budget. Turning `daily_minimum_buy_enabled` off produced no entry over three repeated evaluations for either value of the retired forced-order flag; status was `no_trade`, buy count remained zero. These runs exercise current source logic with a fake account and market data. The first dry-run order is not presented as a real fill, and no claim is made about binary identity with the historical EXE.

Direct policy and replay runs establish B/C hold on score-zero/no-entry conditions; C vetoes simultaneous qualifying buy/sell scores; repeated, revised, or stale completed bars cannot release C's general signal gate; a new completed bar does. A same-bar fresh price still triggers the hard stop, and future/incomplete indicator bars do not suppress valid current-mark protection or manufacture an ATR stop. Acceptance, expiry, partial-fill, and duplicate-notification regressions distinguish attempted orders from completed one-share entries.

Every actual daily protocol independently matches the frozen common limits: 1% risk, one share, one-share maximum, $35 maximum buy, 50% single/total exposure, 5% cash buffer, 2% daily new-buy loss halt, and ₩80,000 starting capital. Stop 3%, take profit 5%, trailing activation 2%/drop 1%, ATR(14) stop 3×/profit 5× remain unchanged. A excludes the historical minimum-entry 5% risk override; it is a matched-risk proxy. No test or report warrants relaxing these limits.

## Independent accounting and provenance

The QA checker imports no application calculation helpers. It reads simulated CSVs and public market inputs with standard-library CSV/JSON, reconstructs each ledger, and compares with a tolerance of **$0.00000001**.

- **42 daily policy/split/cost groups**: every fill notional, quantity, commission/minimum commission, entry fee allocation, gross/net realized P&L; every equity-curve cash balance; independently marked open positions using public close prices; final realized plus unrealized P&L; fee/execution-cost totals; USD and historical-FX KRW return; complete-month flags and target-month counts all reconcile. All buy fills respect one share and $35. Signal timestamps precede fill timestamps, and no simulated shorts or pyramiding appear.
- **6 intraday policy/cost groups**: reconstructed every cash balance, checked equity against held-position decision marks, reconciled fees, execution costs, realized/unrealized P&L, holding times, conflicting-entry joins, and five-minute-grid general exits. Intraday raw private inputs were deliberately not opened or independently rehashed. Source hashes here are recorded provenance; simulated output hashes and protocol hash were independently checked.
- For daily runs, protocol self-hashes, input OHLC hashes, profile hash, costs hash, and public FX hash all match current files. Manifest equals the protocol's embedded manifest. Summary keys are unique and cover exactly three policies × two costs × available splits. Snapshot all output hashes in [artifact-snapshot.json](qa/artifact-snapshot.json).
- Checked public dividend ex-dates against simulated overnight holding intervals across all three daily groups: **zero eligible holdings across dividend ex-dates**. Main fills are HIVE, which has no dividend event in the public manifest. Therefore omitted dividend cash has no direct ledger contribution for these recorded simulated positions. This does not establish total-return equivalence or remove price-adjustment/signal limitations.

Reproduce arithmetic with `python docs/entry-policy-audit-20260929/qa/reconcile_outputs.py` and `python docs/entry-policy-audit-20260929/qa/reconcile_intraday.py`. Machine-readable results: [daily reconciliation](qa/reconciliation.json), [intraday reconciliation](qa/intraday-reconciliation.json). QA scripts compile and the programming rule checker reports no violations in all three scripts.

## Real-data effect and its limits

The post-corporate-action main daily evaluation covers **2026-04-09 through 2026-09-28** after fixed 64-bar warmup. Train and validation are unavailable; original split boundaries were not moved. The action-free KDP/HIVE pair and SPY control are separate outputs, not substitutes for the main historical selection process.

| Main daily case | A | B | C |
|---|---:|---:|---:|
| Base completed round trips | 2 | 2 | 2 |
| Base net USD P&L | -0.0122008691 | -0.0122008691 | -0.0122008691 |
| Base USD return | -0.0225638% | -0.0225638% | -0.0225638% |
| Forced-entry fills | 0 | 0 | 0 |
| Stress executions | 0 | 0 | 0 |
| Complete months meeting +10% USD | 0 / 4 | 0 / 4 | 0 / 4 |

April and September are partial months; the four full calendar windows are May–August. Observed zero successes are not a probability estimate. Shared 1% sizing masks the forced-entry distinction in this main sample. Identical outcomes do not disprove the reproduced engine cause or establish a strategy benefit. Cash-only stress runs show zero USD trading return; their KRW changes are FX translation, not trading skill. Main base KRW return of about -8.237% must not be substituted for the much smaller USD strategy return.

The short intraday comparison covers only four regular sessions, **2026-09-23, 24, 25, 28**. Five-minute labels have a conservative availability lag because provider start/end semantics are unconfirmed. They are simulated grid timestamps, not actual historical broker executions.

| Intraday base case | A | B | C |
|---|---:|---:|---:|
| Completed round trips | 8 | 8 | 2 |
| Entries with qualifying sell signal | 6 | 6 | 0 |
| General exits on next five-minute grid step | 5 | 5 | 0 |
| Net equity change USD | -0.3956582625 | -0.3956582625 | -0.2363769750 |
| USD period return | -0.6707129% | -0.6707129% | -0.4007021% |

C removes the observed conflicting entries and next-step general exits and loses less in this short sample. It still loses money. A/B each retain **-$0.0426875 unrealized net P&L**, included above; reporting only closed P&L would overstate their result. Every stress case has zero executions. Forced fills are zero under shared 1% limits. There are zero complete calendar months, so monthly return, monthly worst return, and literal historical five-minute-exit fields remain blank. No monthly target, future probability, or profitability conclusion is supported.

## Scenario coverage and boundaries

Brainstormed 25 scenarios before running the app, then added seven fresh-eye edge cases. [Scenario checklist](qa/scenarios.md): 16 P0, 14 P1, 2 P2. All 32 reviewed/executed to their stated scope; the concurrency boundary above remains explicitly untested.

| Scenario IDs | Execution / evidence | Result |
|---|---|---|
| 01–04 | Actual CLI help/smoke/repeat; byte hashes; runtime network-denial regression | PASS |
| 05–10 | Actual engine forced/no-force toggle; policy conflict/dedup/protection and replay regressions | PASS |
| 11–16 | Independent protocols, hashes, all daily ledgers/curves, malformed-data CLI, full-month checks | PASS |
| 17–20 | Actual CLI provenance/interval/value/profile/warmup/cohort rejection cases | PASS |
| 21 | Fill timing, unfilled/partial/deduplicated-fill regressions and CSV ordering | PASS |
| 22–25 | Separate cohort protocols, zero-execution labels, ledger position sequence, scope limitations | PASS |
| 26–28 | FX rejection cases; stale/future/naive timestamp regression and original CLI repro; manifest/split/key checks | PASS |
| 29–30 | Empty CSVs read as zero rows; interrupted/nonempty output protection, serial atomicity boundary documented | PASS |
| 31–32 | Session fill bookkeeping and repeated/new-bar tests; independent fee/minimum/open-position reconciliation | PASS |

No private account/order ledger, credentials, broker connection, network fetch, GUI, EXE, or scheduler was accessed by this QA lane. Only QA-owned documentation/scripts/artifacts were changed. Requested evidence is retained; there is no production instrumentation. No unresolved P0/P1 blocker remains in this QA scope. Automatic approval review initially rejected recursive cleanup of the generated QA `__pycache__` directory with the stated reason “blocked by policy”. The parent subsequently listed its contents and safely removed exactly four generated `.pyc` files using explicit, nonrecursive `Remove-Item -LiteralPath` calls. The directory is now empty; no source or evidence files were removed.
