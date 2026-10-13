# Entry-policy hands-on QA scenarios

Prepared before application execution on 2026-09-29. Scope: offline CLI, engine fake regression, policy transitions, and public-market simulated outputs. Never read private actual-order ledgers.

| ID | Priority | Steps / expected behavior | Result |
|---|---|---|---|
| 01 | P0 | Run CLI help; describe offline-only A/B/C and expose required inputs. | PASS — see review-qa.md for execution evidence and limits |
| 02 | P0 | Run synthetic smoke in fresh QA directory; emit frozen protocol and all expected outputs. | PASS — see review-qa.md for execution evidence and limits |
| 03 | P0 | Re-run exact output directory; reject reuse and preserve every prior byte. | PASS — see review-qa.md for execution evidence and limits |
| 04 | P0 | Attempt socket and subprocess operations after loading CLI; both denied before access. | PASS — see review-qa.md for execution evidence and limits |
| 05 | P0 | Replay current engine with fake broker: low buy score 0 forces entry, followed by technical sell at +5 minutes. | PASS — see review-qa.md for execution evidence and limits |
| 06 | P0 | Disable minimum entry in same fake setup; no forced entry. | PASS — see review-qa.md for execution evidence and limits |
| 07 | P0 | B zero-buy condition; hold/no_trade is normal and no quality conclusion follows. | PASS — see review-qa.md for execution evidence and limits |
| 08 | P0 | C simultaneous sell signal veto; no conflicting entry. | PASS — see review-qa.md for execution evidence and limits |
| 09 | P0 | C repeated completed-bar general signal; deduplicate while protective exits remain evaluated. | PASS — see review-qa.md for execution evidence and limits |
| 10 | P0 | Protective stop/profit/trailing/ATR thresholds equal frozen legacy values for A/B/C. | PASS — see review-qa.md for execution evidence and limits |
| 11 | P0 | Compare all actual protocols against frozen 1%, one share, $35, 50% exposure, 5% cash assumptions. | PASS — see review-qa.md for execution evidence and limits |
| 12 | P0 | Independently reconcile each simulation fill ledger to final cash and fees. | PASS — see review-qa.md for execution evidence and limits |
| 13 | P0 | Independently reconcile realized plus unrealized net P&L to ending equity less initial capital. | PASS — see review-qa.md for execution evidence and limits |
| 14 | P0 | Snapshot protocol hash and input hashes; verify source files against manifest where available. | PASS — see review-qa.md for execution evidence and limits |
| 15 | P0 | Reject malformed/nonfinite OHLC and duplicate bars rather than emitting valid experiment results. | PASS — see review-qa.md for execution evidence and limits |
| 16 | P0 | Confirm partial calendar months never become complete-month evidence or future probabilities. | PASS — see review-qa.md for execution evidence and limits |
| 17 | P1 | Reject missing required historical arguments and wrong bar interval. | PASS — see review-qa.md for execution evidence and limits |
| 18 | P1 | Reject zero/negative/nonfinite USDKRW and negative/nonfinite operating costs. | PASS — see review-qa.md for execution evidence and limits |
| 19 | P1 | Reject modified frozen risk, policy list, exits, or capital. | PASS — see review-qa.md for execution evidence and limits |
| 20 | P1 | Reject insufficient per-symbol warmup and missing frozen cohort symbols. | PASS — see review-qa.md for execution evidence and limits |
| 21 | P1 | Verify next-bar fills and same-bar nonfills; distinguish rejected forced attempts from completed buys. | PASS — see review-qa.md for execution evidence and limits |
| 22 | P1 | Validate main post-action data and separate action-free/SPY controls are correctly labeled and bounded. | PASS — see review-qa.md for execution evidence and limits |
| 23 | P1 | Identify zero executions separately from zero return, including fees/cost assumptions. | PASS — see review-qa.md for execution evidence and limits |
| 24 | P1 | Cross-check buy/sell quantities, price bounds, and ledger sequence prevent shorts or pyramiding. | PASS — see review-qa.md for execution evidence and limits |
| 25 | P1 | Confirm actual historical daily simulation does not claim literal five-minute mechanism or exact historical 5% risk execution. | PASS — see review-qa.md for execution evidence and limits |

Fresh-eye augmentation:

| ID | Priority | Steps / expected behavior | Result |
|---|---|---|---|
| 26 | P1 | Reject duplicate/malformed FX dates and late FX coverage; avoid silent future FX lookahead. | PASS — see review-qa.md for execution evidence and limits |
| 27 | P1 | Validate stale, reversed, or timezone-naive completed-bar input is handled explicitly. | PASS — see review-qa.md for execution evidence and limits |
| 28 | P1 | Check manifest and protocol metadata agree with summary keys and unavailable split reporting. | PASS — see review-qa.md for execution evidence and limits |
| 29 | P2 | Check empty fills/reasons CSVs can be read safely without inventing transactions. | PASS — see review-qa.md for execution evidence and limits |
| 30 | P2 | Examine interrupted-output ambiguity and atomicity limits; document rather than assume concurrency safety. | PASS — see review-qa.md for execution evidence and limits |
| 31 | P1 | Check cross-symbol/current-session dedup does not suppress next-session entry or hard protection. | PASS — see review-qa.md for execution evidence and limits |
| 32 | P1 | Reconcile stress/base fee formulas, minimum fee, and final open-position entry costs independently. | PASS — see review-qa.md for execution evidence and limits |
