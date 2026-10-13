# QA failure journal

All retained files under this QA directory are explicitly requested review evidence, not production instrumentation. No private ledger was read. No production debugger, broker, authentication, network, GUI, scheduler, or executable was invoked.

## Date-only completed-bar timestamp acceptance

Observed actual CLI result: a copy of public SPY daily CSV with row 80 changed from an explicit timezone close to `2024-12-26` exited 0 and wrote summary.csv. Expected rejection. `cli-cases/date-only.csv`, `cli-cases/date-only.txt`, and its output directory preserve evidence.

Hypotheses and distinguishing evidence:

1. The CLI could ignore the changed bars path. Inspect generated `protocol.json` bars SHA-256 and compare to the mutated input. A matching hash falsifies this hypothesis.
2. The generic CSV boundary could convert date-only to timezone-aware midnight before the strategy sees it. Load only the CSV module through the offline CLI import and observe row 80 timestamp. Midnight UTC confirms this hypothesis.
3. The policy itself could allow a raw date-only completed-bar identity. Existing direct-policy runtime regression rejects date-only unless supplied a separate explicit completed-bar identity; that falsifies raw-policy acceptance as the cause.

Fix ownership: source implementation owner through parent agent. QA only reruns the actual CLI in a fresh directory and retains failing and passing evidence. No instrumentation added to production modules.

## Pre-existing nonempty output without protocol

Observed first offline suite: both daily CLI and intraday replay overwrote a sentinel summary.csv, 2 failures. Existing protocol directory refusal worked and exact QA smoke output hashes remained unchanged on refused repeat.

Hypotheses: blanket overwrite (falsified by protocol-present refusal), protocol-only existence gate (confirmed by protocol-absent sentinel reproduction), or fixture path error (falsified by sentinel assertion and CLI output target). Implementation owner corrects both entry points and the shared writer boundary. Preserve `offline-tests.txt` as failing-first evidence and write rerun separately.

Final verification: 25 actual CLI rejection scenarios pass (cli-cases-expanded.json); date-only now rejected before summary. Targeted final offline suite: 54 passed in 12.17s. No production instrumentation, listeners, temporary environment overrides, or debugger sessions were created. All retained QA files are requested evidence. Raw-to-normalized timestamp and correct mutated input hash recorded in timestamp-runtime.json.
