# Local early-exit investigation, 2026-09-29

User authorized source fixes, tests and offline experiments, not deployment or trading. Existing dirty working tree and `.debug-journal.md` are preserved. This file is the task-specific evidence ledger.

## Scope and acceptance

1. Verify source, executable, current settings and active execution separately.
2. Classify only actual fills; absent fill prices/costs or state remain unknown.
3. Test A–F before source fixes. Keep live policy defaults/settings intact; corrected strategy behavior is opt-in for offline experiments.
4. Common corrected execution engine for all predeclared candidates. No hindsight-selected universe or silently assumed FX/fees. No-trade results cannot support a strategy claim.
5. Deliver risk budgets, returns including open holdings, monthly/exit metrics if comparable data exist, otherwise runnable procedure and exact missing fields.

## Hypotheses and distinguishing evidence

- H1 configuration/path mismatch: GUI effective stop differs from user's 5%, source settings differ from installed binary settings. Verify allowlisted effective runtime and launcher paths.
- H2 independent ATR/trailing/signal exits bypass perceived fixed stop: reproduce 10/ATR .02/3, conflicting scores and 100→102→100.98 in isolated strategy tests. Actual causation requires matching filled order and decision receipt.
- H3 evaluation artifact: qty order absent from generic backtester and learning backtester uses a separate strategy. Reproduce actual executed qty and compare call graph, not headline return.
- H4 order lifecycle/data issues: inspect receipts for partial fills, timestamp/quote provenance, stale cost basis, duplicate submissions. Unknown unless recorded.

## Safety and artifacts

- No live process attached, no order/cancel API, no scheduler start or edits.
- Tests use process-local network denial; GUI/live factory not launched.
- New reports contain only allowlisted operational facts, no raw `.env`, account numbers, tokens or session ids.
- Reproduction/QA outputs under this report directory are requested durable evidence, not debug prints. No breakpoints/listeners introduced.
- Python 3.14.2; requirements-test.txt uses pytest 9.1.1. No pyproject.toml exists.
- CommitLore CLI unavailable (`command -v commitlore` yielded no executable); do not install or infer history. Current local files remain authoritative.

## Review criteria

BOOMER-6: correctness of prices/units/fees; omissions at missing ATR/restarts/partial fills; minimal use of existing structure; separate responsibilities; bounded runtime; no live/credential risk. Final reviews must independently inspect these boundaries.


## Final hypothesis findings and verification

- H1 confirmed for saved configuration: deployed GUI fixed stop is 3%, different from the assumed 5% and source-root dry-run configuration. KIS live settings were read through allowlisted fields. No account API or executable was launched; binary/source equivalence remains unverified.
- H2 reproduced: independent ATR can trigger at 9.94 for entry10/ATR.02x3; same-bar conflicting scores can buy/sell/buy; activated legacy trailing can disappear below entry. Recent three recorded submission pairs instead identify daily-minimum entry followed by ordinary technical sell. Actual filled cause/PnL is not proven.
- H3 confirmed and corrected in the generic CSV path: quantity buy was omitted, additional holdings were overwritten, and high-water was not updated. The learning BacktestEngine is separate and not fixed by these changes.
- H4 remains unknown for real fills: no adequate complete-roundtrip receipts, fees, quote source timestamps or fill-version state. New diagnostics preserve missing values explicitly; they cannot reconstruct historical facts.
- Review also reproduced postsubmission diagnostic exceptions, additional-fill retained-stop risk mismatch and emergency-stop drift. All were corrected and retested. Existing automatic authorization and protected-sale policy limits remain intact.
- Final root verification: 437 passed / 29 subtests in 93.40s. Import-only cleanup then Ruff clean, compile exit0, 91 focused tests passed in 7.50s. Counts overlap and are not summed.
- Independent review lanes goal/code/security/context/QA all PASS. CLI manual QA and independent arithmetic reconciliation are in review-qa.md; all price/FX outcomes remain synthetic-only evidence.
- Implementation complete within offline scope. No investment-performance conclusion, deployment, trading, scheduling, paid service, credential output or git commit. See VERIFICATION.md for exact commands and changed-file ownership.
