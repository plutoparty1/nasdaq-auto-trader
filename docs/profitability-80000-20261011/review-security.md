# Security and scope review

Verdict: **PASS**. Confidence: high for the reviewed offline CLI and preserved-file boundary. No blocking security or scope issue found.

Reviewed 2026-10-11: `nasdaq_auto_trader/profitability*.py`, the optional profitability route in `scripts/run_entry_policy_comparison.py`, the separate experiment profile, relevant test paths, and the before-task preservation snapshot. This lane verifies isolation and preservation; it does not certify profitability or live execution safety.

## Evidence

- `scripts/run_entry_policy_comparison.py:23` installs the existing audit hook before application-module imports. Socket events, HTTP connect/request events, and subprocess spawning are rejected. Lines 37–40 expose pure package modules without executing the application package initializer. The new optional route imports only the offline experiment runner.
- Runtime exercise of the complete twelve-profile synthetic CLI produced 18 temporary result files with `SYNTHETIC_SMOKE_ONLY`. Loaded live broker/engine/config/session/controller modules: **0**. Sensitive-file opens matching `.env`, `trading_config.json`, credential/secret/ledger/token-cache names: **0**. Explicit socket creation and subprocess spawning after the run both raised the expected forbidden-access error. This synthetic execution checks software plumbing only.
- `python scripts/run_offline_tests.py -q tests/test_profitability_cli.py tests/test_entry_comparison_cli.py`: **6 passed in 19.69s**, including original CLI isolation, preserved output sentinels, and rejection of modified profitability profiles before result creation.
- `profitability_config.py:17` checks the separate profile SHA-256, the three preexisting experiment configuration hashes, and historical bars/FX hashes. The runner fixes historical split boundaries, rejects an unverified operating-charge override, marks historical results `EXPLORATORY_ALREADY_USED_DATA`, and records `no_independent_holdout=true`.
- `run_entry_policy_comparison.py:102`, `profitability_experiment.py:60`, and `profitability_legacy.py:197` reject nonempty output directories. New writes consist of simulation artifacts in the requested output directory. No new module calls a broker, reads live credentials, schedules tasks, launches a resident process, replaces an EXE, or writes live settings.
- Recomputed every entry in `preservation-before.json`: **890 files checked, 0 missing, 889 unchanged**. The sole changed existing file was the explicitly authorized optional CLI extension, `scripts/run_entry_policy_comparison.py`. Existing tracked and untracked work, original experiment configurations and datasets, and the captured live configuration remained byte-identical. Snapshot contents and private file contents were not included in this review.
- No staging, commit, reset, deployment, order, cancellation, or task-scheduler operation was performed by this reviewer. The only durable file written by this review is this report. Test outputs used temporary directories.

## Scope limits

- The runtime file-open probe used sensitive-name categories and the reviewed import/call graph; it is not an operating-system sandbox or a claim about arbitrary untrusted Python code.
- The preservation check covers the 890 files captured before work. It cannot attest to files outside that recorded set. Final aggregate verification should repeat the same hash comparison after all reporting changes finish.
- Frozen profile SHA-256: `69e6addc681961af86e2d08ca3f2188aa67ed5fe37dacefa234d86f31eff20a1`. Financial statistics, adequacy of market data, and candidate selection are reviewed in the other lanes and final report.

Blocking issues: none.
