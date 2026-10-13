# Independent security review — 2026-09-29

Verdict: **PASS — all identified boundary defects were fixed and independently rechecked**.

Scope: the research KIS/public transports and collectors, the offline entry comparison CLI, and the added intraday replay output boundary. Only this review document was edited by this reviewer. No authenticated network request was performed; no credential file body or private order ledger was opened. Tests used synthetic credentials, temporary output directories, and fake connections or a network-denying audit hook.

## Findings

1. **Fixed and verified: comparison output overwrite.** A preexisting `synthetic-bars.csv` in a temporary directory without `protocol.json` was initially overwritten, and the CLI exited 0. Both the CLI and shared suite writer now reject a nonempty destination. Synthetic input generation uses a temporary staging directory. The same independent reproduction now exits nonzero, preserves the sentinel exactly, and creates no output files. The CLI regression and normal smoke run passed.
2. **Fixed and verified: dotenv precedence.** The collector initially selected the first duplicate key inside one dotenv, whereas `gui_launcher._read_dotenv()` selects the last duplicate before applying process/local-app/app/parent-file precedence. The collector now parses a per-file map, then applies cross-file `setdefault`. The same isolated synthetic duplicate-key reproduction changed from `matches_launcher_last_value=false` to `true`; the new regression and existing process/file precedence test both passed. The reviewer did not read actual credential values.
3. **Fixed and verified: public output overwrite.** An existing `CMCSA.yahoo.json` was initially overwritten when `manifest.json` was absent. The collector now rejects nonempty output before network access. An independent sentinel replay returned exit 2, preserved the file, and made zero wire calls. Its CLI regression passed.
4. **Fixed and verified: intraday output overwrite.** The replay now rejects nonempty output before any writes, including when `protocol.json` is absent. The new sentinel regression passed in this review.

## Verified boundaries

- KIS transport uses `ssl.create_default_context()`, the fixed official host and port 9443, a 15-second timeout, and an 8 MB response ceiling. The actual `https_wire()` was exercised with a fake `HTTPSConnection`: one auth POST and three allowlisted query GETs; hostname checking and `CERT_REQUIRED` were asserted. Order, cancel/revise, revoke, and hashkey paths were denied before constructing a connection. URL/transaction-ID/query-key/value checks also run before the client wire call. Redirects are rejected.
- Authentication is limited to one attempt per client; query transport failures/rate limits have a two-attempt ceiling. Collector pagination is finite: 6 history windows × 10 pages, 4 daily symbols × 20 pages, and 3 minute symbols × 10 pages. With the two-attempt query ceiling, the current full driver permits at most 341 request attempts. The token is memory-only and secret-bearing dataclasses suppress field representations. Tested transport/API error messages are sanitized.
- The KIS CLI restricts sanitized summaries to a fresh JSON file in this audit directory and uses exclusive creation. It creates a unique private run directory below `%LOCALAPPDATA%/NasdaqAutoTrader/research/entry-policy-20260929`, rejects a private root resolving inside the repository, and writes raw history only there.
- Public transport validates exact Yahoo/ECB HTTPS hosts, paths, query schemas and permitted period bounds before connection construction. Its actual connection path was exercised with fake connections for both hosts, checking verified TLS, GET method, and only `User-Agent`/`Accept` headers. It does not load KIS credentials or credential modules. Redirects are denied; retries are capped at two.
- Both standalone collection scripts load a pure package namespace and import no live engine, broker, or live config module. The comparison CLI installs its audit hook before research imports. Six separate attempts—socket construction, DNS, socket connection, HTTPS connection, urllib request, and subprocess launch—were denied. No live engine/broker/config module was imported.
- Intraday replay uses the pure backtest path. Its ten focused tests passed with socket/HTTP network operations blocked, including output preservation.

## Test and artifact evidence

The final combined review run passed **72 tests in 12.74 seconds**, covering the five initial files below plus `test_entry_comparison_limits.py` and `test_entry_intraday_replay.py`, with all new regression tests included. Socket/HTTP operations remained blocked in the review test process. The comparison CLI's own network blocker also runs in subprocess smoke tests.

Independent rendered-traceback checks covered transport exceptions, API rejection bodies, and malformed JSON responses containing a synthetic private marker: **3 sanitized cases, 0 marker leaks**. HTTP 429 and API `EGW00201` responses each stopped at exactly two query attempts. Six offline socket/DNS/HTTP/urllib/subprocess probes were blocked, independently of manifest counters.

The initial focused security/data-boundary run passed **51 tests in 8.06 seconds** across `test_research_readonly.py`, `test_research_readonly_collect.py`, `test_research_readonly_boundaries.py`, `test_research_public.py`, and `test_entry_comparison_cli.py`. The reviewer bootstrapped the same pure package namespace used by the CLIs, then denied socket construction/connection/DNS and HTTP/urllib connection audit events. This avoids the ordinary package initializer importing live engine modules during test discovery. An initial broader hook also blocked a local hostname lookup during that initializer; that was a review-harness discovery failure, not a completed product test run.

The intraday suite independently passed **10 tests in 0.50 seconds** under the same network restriction.

Only allowlisted aggregate fields were read from the already-created sanitized acquisition reports:

| Report | Auth | Daily | History | Minute | Order | Cancel |
|---|---:|---:|---:|---:|---:|---:|
| `kis-acquisition.json` | 1 | 24 | 3 | 13 | 0 | 0 |
| `kis-acquisition-final.json` | 1 | 24 | 6 | 16 | 0 | 0 |
| Total reported | 2 | 48 | 9 | 29 | 0 | 0 |

These are reported attempt counters, not independent wire logs. Zero order/cancel fields alone were not treated as proof: endpoint-denial tests and actual transport-path inspection establish the read-only boundary. The public manifest reports zero order/cancel calls and credential reads; the verified GET-only transport and import/header checks support that assertion. Public request attempts are not independently recorded in that manifest.

A final count-only secret-shape scan of 174 repository research artifacts found **0 credential-value, 0 Bearer-token, 0 private-account-value, and 0 private-order-value matches**. No matched text was printed. This is a pattern scan, not a comparison with real credential values; those values were deliberately not read.

No order, cancel, scheduler, daemon, live configuration, or executable changes were made by this reviewer. The safety conclusions apply to the inspected research entry points and ordinary execution; the Python audit hook is not a hostile-code sandbox.
