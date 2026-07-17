# T2: Read-only Intraday Scanner

**PRD Ref**: US-1
**Priority**: P1
**Size**: L
**Status**: Todo
**Depends On**: T1

## Acceptance Criteria

- Scan the packaged Nasdaq-100 through market-data-only capabilities.
- Cap KIS shortlist size at 30, persist an atomic report, and submit zero orders.
- Return explicit rejected reasons and request failures.

## TDD Spec

Test `test_kis_scan_is_bounded_persisted_and_orderless` fails before the scanner
module exists. Implement `ShadowMarketData`, which extends only historical-bar
market data and discovers optional liquidity/quote capabilities. It has no order
method. The fake deliberately includes an order spy as an additional runtime
assertion, while the production function signature is the compile-time boundary.

Files: create `intraday_shadow_scan.py` and `test_intraday_shadow_scan.py`.
Persist `%LOCALAPPDATA%/NasdaqAutoTrader/runtime/intraday_shadow_scan.json` via a
same-directory temporary file and `os.replace`. Schema: UTC `started_at`,
`universe_id`, scanned and eligible symbol lists, per-symbol rejection reasons,
and `submitted_order=false`. Empty shortlists persist a valid empty report;
provider errors propagate to the controller safety boundary.
