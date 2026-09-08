# PRD: Learned Automatic Symbol Selection

**Version**: 0.1
**Author**: Codex
**Date**: 2026-07-10
**Status**: Approved
**Size**: XL

---

## 1. Problem Statement

### 1.1 Background

The desktop trader currently requires a user-selected `ticker`, and the legacy
AI path can only choose from `ai_candidate_tickers` entered by the user. The
AI Quant Lab already has a safer, deterministic runtime that loads a validated
`StrategySpec`, calculates market features, ranks signals, and applies
portfolio and execution risk guards. That learned/validated ranking is not
connected to the normal GUI trading loop or a maintained market universe.

The approved default universe is the Nasdaq-100. Nasdaq describes the index as
100 of the largest Nasdaq-listed non-financial companies and now performs
quarterly reviews in addition to annual reconstitution. The June 2026 review
changed five constituents, so a timeless hard-coded ticker list is not an
acceptable source of truth.

References:

- [Nasdaq-100 2026 methodology](https://indexes.nasdaqomx.com/docs/methodology_NDX.pdf)
- [Nasdaq-100 June 2026 quarterly changes](https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-100-indexr-june-2026-quarterly-changes)
- [KIS Open API documentation](https://apiportal.koreainvestment.com/apiservice)
- [KIS official Open API examples](https://github.com/koreainvestment/open-trading-api)

### 1.2 Problem Definition

When automatic selection is enabled, the application must select candidate
symbols from a maintained Nasdaq-100 universe using a mode-eligible, validated
StrategySpec, then allow only existing deterministic strategy and
risk gates to create an order. The user must not have to enter a ticker or AI
candidate list for that cycle.

### 1.3 Impact of Not Solving

Without this feature, the user remains the effective universe selector, which
creates selection bias and prevents unattended research/paper cycles. A naive
implementation would be worse: it could scan stale or untradeable securities,
overload KIS rate limits, skip held-position exits, or let an LLM response
submit a live order directly.

## 2. Goals & Non-Goals

### 2.1 Goals

- [ ] G1: With automatic selection enabled, select one or more symbols without
  reading `TradingSettings.ticker` or `ai_candidate_tickers` for entry
  candidates.
- [ ] G2: Rank a bounded, liquid Nasdaq-100 shortlist with the highest-scoring
  mode-eligible StrategySpec and return scores, reasons, universe effective
  date, and block reasons in every selection report.
- [ ] G3: Preserve all current risk, market-hours, buying-power, position,
  daily-loss, cooldown, restart-safe duplicate suppression, durable pre-order
  audit, and bounded live-confirmation gates before broker submission.
- [ ] G4: Fail closed with zero submitted orders when the universe,
  mode-eligible strategy, market data, ranking, or liquidity checks are
  unavailable or invalid.
- [ ] G5: Keep selection latency below 60 seconds at p95 for KIS by scanning no
  more than 30 liquid candidates per cycle and reusing a fresh selection cache
  only in preview, dry-run, and paper modes. Live reranks current data.
- [ ] G6: Expose automatic selection status and reasons in the desktop GUI and a
  read-only CLI preview without exposing a new GUI live-order command.

### 2.2 Non-Goals

- NG1: Guarantee profit, suitability, or future model performance.
- NG2: Train a neural network, reinforcement-learning agent, or online model in
  the live execution process.
- NG3: Let an LLM recommendation bypass `ai_direct_order_disabled`.
- NG4: Scan the entire Nasdaq Composite, OTC securities, options, short sales,
  leveraged products, or margin positions.
- NG5: Enable live trading by default or remove `--confirm-live-orders`.
- NG6: Automatically download and execute remote code or an unvalidated remote
  strategy artifact.
- NG7: Add a database; JSON snapshots, JSON cache, and existing JSONL audit logs
  remain the storage surfaces.

## 3. User Stories & Acceptance Criteria

### US-1: Automatic Universe Selection

**As a** trader, **I want** the system to choose from the Nasdaq-100, **so that**
I do not manually pick a ticker before each cycle.

**Acceptance Criteria:**

- [ ] AC-1.1: Given `auto_symbol_selection_enabled=true`, when a cycle starts,
  then entry candidates come from the validated Nasdaq-100 snapshot and not
  from `ticker` or `ai_candidate_tickers`.
- [ ] AC-1.2: Given duplicate, malformed, empty, or more than 120 universe
  symbols, when the snapshot loads, then selection is blocked before market
  data or broker construction.
- [ ] AC-1.3: Given a snapshot older than 120 days, when mode is live, then the
  cycle submits zero orders with `universe_snapshot_stale`; dry-run and paper
  return an explicit stale warning.
- [ ] AC-1.4: Given the June 22, 2026 snapshot, then ALAB, CRWV, NBIS, RKLB, and
  TER are present while CHTR, CTSH, INSM, VRSK, and ZS are absent.

### US-2: Learned Strategy Ranking

**As a** trader, **I want** candidates ranked by a learned and validated
strategy, **so that** selection follows historical evidence instead of a manual
watchlist.

**Acceptance Criteria:**

- [ ] AC-2.1: Given a valid mode-eligible StrategySpec and complete bars, when
  selection runs, then `calculate_feature_rows`, `build_strategy`, and
  `rank_and_select` determine ranked symbols.
- [ ] AC-2.2: Given identical universe, bars, StrategySpec, and clock, when
  selection runs twice, then selected symbols, order, scores, and reasons are
  identical. Universe inputs and bar mappings are normalized by symbol, and
  feature ranks and final signal ranks use symbol ascending as their secondary
  key so provider ordering cannot break ties.
- [ ] AC-2.3: Given no mode-eligible registry record, rollback/no-trade status,
  invalid spec, or missing required features, then selection is blocked. When
  valid inputs produce no score meeting the entry threshold, the result is
  `no_trade`. Neither result falls back to a manual ticker.
- [ ] AC-2.4: Dry-run and paper may select only from `PAPER_CANDIDATE`,
  `PAPER_TRADING`, `SHADOW_LIVE`, or `CHAMPION`; live additionally requires a
  promoted `CHAMPION` with `manual_approval=true` and
  `allowed_for_live=true`, otherwise zero live orders are submitted.

### US-3: Liquidity and Tradability Shortlist

**As a** trader, **I want** illiquid or unavailable symbols removed before
historical ranking, **so that** API limits and execution risk stay bounded.

**Acceptance Criteria:**

- [ ] AC-3.1: Given KIS market data, when selection starts, then the client uses
  an official overseas trading-value/liquidity ranking and intersects it with
  the Nasdaq-100 snapshot before fetching historical bars.
- [ ] AC-3.2: Given Alpaca market data, when selection starts, then multi-symbol
  bars may be fetched in one batch and filtered using existing volume, spread,
  and staleness rules.
- [ ] AC-3.3: Given KIS rate limiting, when `EGW00201` occurs once, then the
  existing bounded retry applies; repeated rate-limit or malformed ranking
  responses block selection without partial ordering.
- [ ] AC-3.4: The historical shortlist contains at most 30 symbols and every
  selected symbol has a positive price, sufficient bar history, acceptable
  dollar volume, and non-abnormal spread before ordering.
- [ ] AC-3.5: For a Nasdaq-100 KIS cycle, ranking, bars, quotes, buying-power
  checks, and order submission carry one validated Nasdaq exchange identity.
  `price_exchange_code` and `order_exchange_code` must resolve to the accepted
  KIS Nasdaq code pair (`NAS`/`NASD`); any mismatch blocks before ranking and
  submits zero orders.

### US-4: Safe Automatic Orders

**As a** trader, **I want** automatic selection to use existing order controls,
**so that** a high rank cannot bypass portfolio risk.

**Acceptance Criteria:**

- [ ] AC-4.1: `TradingEngine` is the sole order-construction and submission
  owner for this feature. A selected entry symbol passes through the existing
  technical buy decision, RiskManager, settings guard, market-hours gate, an
  AI Quant readiness/live guard immediately before `_submit_or_block_order`,
  and broker response validation. The selector and AI Quant `LiveEngine` must
  not submit automatic-selection orders.
- [ ] AC-4.2: Every currently held symbol is evaluated for exits even when it is
  absent from the current entry shortlist.
- [ ] AC-4.3: Dry-run produces candidate orders through `DryRunBroker` only;
  paper uses the broker paper endpoint; live requires live config,
  `allow_live_trading`, a promoted `CHAMPION` StrategySpec with manual/live
  approval, AI Quant live gates, and `--confirm-live-orders`. Live automatic
  orders also require the explicit session authorization defined by
  `PRD-session-scoped-live-authorization.md`: one NASDAQ market date, at most
  12 actual order attempts, and bindings to strategy ID/version/spec digest,
  universe version, risk-config digest, execution mode, and broker identity.
  A session/date/attempt/binding mismatch blocks the next order.
- [ ] AC-4.4: The desktop GUI can start dry-run/paper automatic cycles but does
  not gain a new `live start` or `execute live` button.
- [ ] AC-4.5: The legacy LLM AI route still returns
  `ai_direct_order_disabled` when it attempts a direct order.
- [ ] AC-4.6: After each accepted buy in a cycle, its notional and quantity are
  reserved before sizing the next candidate. Sells do not release reusable
  cash in the same cycle, and aggregate accepted buys cannot exceed the
  cycle-start cash, buying power, position, or exposure limits.
- [ ] AC-4.7: Daily order counts, cooldown timestamps, and submitted signal
  identities persist atomically across loop iterations and process restarts.
  An automatic live order uses an idempotency key derived from market date,
  strategy ID/version, symbol, side, and signal timestamp. Under an
  inter-process lock, the key must compare-and-set from `new` to `submitting`
  and persist before broker access, then transition to `submitted`, `rejected`,
  or `uncertain`. `submitting` found after a restart becomes `uncertain`;
  `submitting`, `submitted`, `rejected`, and `uncertain` are terminal for that
  key and block automatic retry, so the same key cannot reach the broker twice.
  After operator reconciliation, a retry requires a genuinely new signal
  timestamp and therefore a new idempotency key.
- [ ] AC-4.8: Every automatic live order intent must be appended durably to the
  audit ledger before broker submission. An append failure returns
  `audit_log_write_failed` and makes zero broker calls; the eventual broker
  outcome is written as a separate post-order event.
- [ ] AC-4.9: Live mode never uses a persisted ranked/selected-symbol report as
  order input. It reloads current market data and reruns ranking each cycle;
  unreadable or modified cache content is ignored and cannot reach the broker.

### US-5: Operator Transparency

**As an** operator, **I want** to see what was selected and why, **so that** I
can audit automated behavior.

**Acceptance Criteria:**

- [ ] AC-5.1: The GUI settings surface provides one toggle labeled
  `과거 데이터 기반 종목 자동 선택`; manual ticker fields remain available
  only when the toggle is off.
- [ ] AC-5.2: The dashboard log reports universe effective date, resolved
  strategy ID/version, shortlist count, selected symbols, scores, reasons, and
  any block reason in plain Korean.
- [ ] AC-5.3: `select-symbols --trading-config <path>` prints a JSON selection
  report and always sets `submitted_order=false`.
- [ ] AC-5.4: Cache and audit files contain no API keys, access tokens, account
  number, cash balance, or buying power.
- [ ] AC-5.5: The PyInstaller build bundles the validated default universe and
  selector modules, launches without source files installed, and excludes
  `.env`, `.kis_token.json`, runtime cache, registry, and audit data.
- [ ] AC-5.6: A fresh EXE resolves a writable external
  `strategy_artifact_root` under the application data directory and shows
  `학습 완료 전략 없음` without ordering until the existing research,
  backtest, validation, and paper-promotion workflow creates an eligible
  registry record and StrategySpec. No live-approved seed artifact is bundled.

## 4. Technical Design

### 4.1 Architecture Overview

```text
Nasdaq-100 snapshot + metadata
              |
              v
UniverseSnapshotRepository ----> liquidity/tradability shortlist
                                         |
                                         v
                                  historical bars
                                         |
                                         v
ModeEligibleStrategySelector -> features -> StrategySpec rank_and_select
              |                          |
              |                          +-> SelectionReport
              v
selected entry symbols + held exit symbols
              |
              v
TradingEngine: TechnicalStrategy -> RiskManager -> settings/market gates
              |
              v
AI Quant readiness/live guard -> durable intent audit -> idempotency guard
              |
              v
      DryRun / paper / explicitly confirmed live broker
```

New ownership boundaries:

- `quant_data/universe_snapshot.py`: strict parsing and staleness policy for a
  versioned Nasdaq-100 JSON snapshot.
- `quant_data/symbol_selector.py`: deterministic mode/status-eligible strategy
  resolution, ranking, and `SelectionReport`; no broker dependency and no
  order submission.
- `quant_data/defaults/nasdaq_100_universe.json`: source URL, effective date,
  membership, optional published weights, and checksum/version.
- `quant_data/resources.py`: source and PyInstaller-frozen resource resolution
  through `importlib.resources`, with strict missing-resource errors.
- `brokers/kis_market.py`: KIS overseas trading-value shortlist adapter.
- `engine_cycle.py`: auto-selection orchestration, selected-entry processing,
  and mandatory held-symbol exit processing.
- `config_runtime.py` and `engine_portfolio.py`: allow auto mode without a
  manual entry ticker and order the cycle as load positions, resolve entry
  universe, union held symbols, then fetch/reuse bars.
- `engine_orders.py`: sole automatic-order submission path, AI Quant readiness
  guard, durable intent audit, bounded live authorization, and idempotency
  checks immediately before broker access.
- `trading_session_store.py`: atomic, account-value-free persistence for daily
  counters, cooldowns, and submitted signal keys across restarts, with a
  cross-process file lock and compare-and-set order-claim transitions.
- `engine_types.py`: typed selection report on cycle results.
- `config_settings.py`, `config_storage.py`, `config_validation.py`: persisted
  feature toggle with backward-compatible default `false`.
- `settings_window_fields_advanced.py` and dashboard rendering modules: toggle
  and plain-language selection output under the existing `DESIGN.md` safety
  contract.
- `cli_parser.py` and `cli_commands_special.py`: read-only `select-symbols`
  preview.
- `ai_quant_lab/operator_models.py` and runtime path construction: writable
  external `strategy_artifact_root` shared by GUI and CLI.
- `NasdaqAutoTrader.spec` and `scripts/build_gui_exe.ps1`: explicitly include
  the default universe resource while excluding runtime strategy/state data.

The selector consumes validated artifacts but never submits an order. The
existing `TradingEngine` remains the only owner of order construction and
submission. AI Quant `LiveEngine` is not invoked by this feature.

### 4.2 Data Model Changes

```text
UniverseSymbol
- symbol: uppercase validated ticker
- index_weight_pct: optional finite non-negative float

UniverseSnapshot
- schema_version: 1
- universe_id: "nasdaq_100"
- effective_date: ISO date
- source_url: official Nasdaq URL
- source_notes: tuple[str, ...]
- symbols: tuple[UniverseSymbol, ...]

RankedSymbol
- symbol
- score
- confidence
- reasons

SelectionReport
- status: selected | no_trade | blocked
- universe_id / universe_effective_date
- strategy_id / strategy_version
- shortlist_count
- ranked: tuple[RankedSymbol, ...]
- selected_symbols: tuple[str, ...]
- warnings: tuple[str, ...]
- blocked_reasons: tuple[str, ...]
- submitted_order: always false on preview
```

Strategy resolution is deterministic and mode-specific:

- A promoted payload with `status=rollback` or `mode=no_trade` is a global
  block and takes precedence over registry candidates.
- Dry-run and paper filter valid registry records to `PAPER_CANDIDATE`,
  `PAPER_TRADING`, `SHADOW_LIVE`, and `CHAMPION`, then order by score
  descending, strategy ID ascending, and version ascending.
- Live resolves only the promoted payload, requires `status=champion`,
  `manual_approval=true`, and `allowed_for_live=true`, and requires an exact
  strategy ID/version match in the spec store.
- A missing, corrupt, non-finite-score, rejected, retired, or spec-mismatched
  record is ineligible; if no eligible record remains, selection blocks.

`strategy_artifact_root` defaults to the platform application-data directory,
not the install directory or PyInstaller temporary extraction directory. It
contains the existing registry, StrategySpec, promoted artifact, and audit
layout. Source runs may override it explicitly for tests. A first run creates
empty directories only; research/promotion remains an explicit existing AI
Quant workflow, and no packaged artifact is implicitly trusted or promoted.

`TradingSettings` adds only `auto_symbol_selection_enabled: bool = False`.
Threshold, top-N, volume, spread, position, and exposure limits remain owned by
the resolved StrategySpec and `AIQuantConfig`; they are not duplicated in GUI
settings.

The latest report for preview, dry-run, and paper is stored below the writable
application-data runtime root at `auto_selection/latest.json` with a 15-minute
TTL. Its cache identity includes broker/provider, execution mode,
universe ID/version/effective date, strategy ID/version/spec digest, registry
and promoted-artifact digest, market session date, and shortlist limit. Any
registry promotion/rollback or identity mismatch invalidates the cache. The
cache is ranking optimization data only and never grants order authorization;
live mode never reads cached ranks or selected symbols as order input and
reranks current market data. Every live order rereads and validates current
promotion state immediately before submission. The cache stores market-derived
selection data only and is written atomically through a temporary sibling file
plus replace.

### 4.3 API Design

No HTTP server API is added.

| Surface | Request | Response | Side effects |
| --- | --- | --- | --- |
| CLI | `select-symbols --trading-config PATH` | `SelectionReport` JSON | Market-data reads and cache write; never an order |
| GUI cycle | saved toggle + normal `자동매매 실행` | existing result rows plus selection report | Dry-run/paper only through GUI |
| CLI once | `--trading-config PATH --auto-select` | existing cycle JSON plus selection report | Live additionally requires `--confirm-live-orders` |
| CLI loop | previous args plus a separately issued session authorization | cycle JSON until stopped/session-blocked | Live requires confirmation and a matching market-date authorization; only actual order attempts consume its maximum-12 budget |
| KIS adapter | `liquid_overseas_symbols(exchange, limit)` | ordered unique symbols | Authenticated GET only |

Example preview response:

```json
{
  "status": "selected",
  "universe_id": "nasdaq_100",
  "universe_effective_date": "2026-06-22",
  "strategy_id": "validated_momentum_001",
  "strategy_version": "1.0.0",
  "shortlist_count": 30,
  "ranked": [
    {
      "symbol": "NVDA",
      "score": 0.82,
      "confidence": 0.78,
      "reasons": ["entry_threshold_passed"]
    }
  ],
  "selected_symbols": ["NVDA"],
  "warnings": [],
  "blocked_reasons": [],
  "submitted_order": false
}
```

The CLI preview exits `0` on `selected` or `no_trade`, `2` on `blocked`, and
never accepts a live confirmation flag.

### 4.4 Key Technical Decisions

| Decision | Options Considered | Chosen | Rationale |
| --- | --- | --- | --- |
| Learned selector | New ML model vs existing validated StrategySpec | Highest-scoring mode-eligible StrategySpec | Reuses audited validation and avoids unverified online training. |
| Direct AI orders | Enable legacy LLM route vs deterministic selector | Keep LLM direct orders disabled | Prompt output cannot become a broker instruction. |
| Universe source | User list, remote page on every cycle, versioned snapshot | Versioned official-source snapshot | Deterministic tests and no runtime dependency on an unstable webpage. |
| Snapshot freshness | Never expire vs warn/block | Warn dry/paper, block live after 120 days | Quarterly membership changes must be operationally visible. |
| KIS performance | Fetch bars for all members vs liquidity shortlist | Max-30 KIS shortlist | Respects rate limits and cycle latency. |
| KIS exchange identity | Independent price/order codes vs end-to-end identity | Validate Nasdaq code pair before ranking | Prevents Nasdaq signals from being submitted to a mismatched exchange route. |
| Existing positions | Rank only entries vs always process holdings | Always process holdings | A position must not lose its exit path when it drops from the shortlist. |
| Order path | Selector, AI Quant LiveEngine, or TradingEngine | TradingEngine only | Preserves current risk/settings behavior while adding one enforceable readiness/live guard. |
| Live loop confirmation | Unbounded flag vs time/cycle vs session/attempt envelope | One NASDAQ market date and 12 actual order attempts | Prevents mid-session wall-clock expiry while bounding actual live-order exposure and requiring next-day reapproval. |
| Learned artifacts | Bundle a seed vs writable external root | Empty external root on first run | Prevents a packaged strategy from being mistaken for live approval. |
| Rank ties | Provider order vs canonical symbol key | Score descending, symbol ascending | Makes equal-score results stable across providers and runs. |
| GUI live behavior | Add live button vs retain current contract | No new live command | Matches `DESIGN.md` and limits accidental live automation. |

## 5. Edge Cases & Error Handling

| # | Scenario | Expected Behavior | Severity |
| --- | --- | --- | --- |
| E1 | Snapshot missing/malformed/empty/duplicate | Block before market data | P0 |
| E2 | Snapshot stale in live mode | `universe_snapshot_stale`, zero orders | P0 |
| E3 | Mode-eligible strategy missing or rollback/no-trade | `eligible_strategy_unavailable`, zero orders | P0 |
| E4 | StrategySpec invalid or required feature missing | Block and audit exact reason | P0 |
| E5 | KIS liquidity response partial/malformed | Reject entire shortlist; no partial trade | P0 |
| E6 | Repeated API rate limit or timeout | Block cycle, preserve prior report only as diagnostic | P1 |
| E7 | No symbol meets threshold | Normal `no_trade` result, zero orders, no alert | P1 |
| E8 | Selected symbol lacks buying power | Existing buying-power guard blocks it | P0 |
| E9 | Selected symbol already held and additional buy disabled | Existing position guard blocks buy | P0 |
| E10 | Held symbol absent from universe | Still fetch bars and evaluate sell | P0 |
| E11 | Cache corrupt or expired | Ignore cache and recompute; if recompute fails, block | P1 |
| E12 | Broker rejects order while returning an ID | Existing response parser treats as not submitted | P0 |
| E13 | Live CLI omits explicit confirmation | `live_order_confirmation_required` | P0 |
| E14 | GUI auto mode with live settings | Selection may render, live order remains blocked | P0 |
| E15 | Multiple buy signals share one account snapshot | Reserve accepted notional/quantity before the next sizing decision | P0 |
| E16 | Cache belongs to another strategy/mode/session | Reject cache and recompute; block if recompute fails | P0 |
| E17 | KIS price/order exchange identities disagree | `kis_exchange_identity_mismatch`, block before ranking | P0 |
| E18 | Pre-order live audit append fails | `audit_log_write_failed`, zero broker calls | P0 |
| E19 | Strategy rolls back after rank cache creation | Invalidate cache and fail fresh live authorization | P0 |
| E20 | Live loop market date/attempt budget is exhausted or a binding changes | Block next order and terminate loop | P0 |
| E21 | Process restarts with an already submitted signal key | Restore state and suppress duplicate broker call | P0 |
| E22 | Fresh EXE has no eligible strategy artifact | Show readiness block; dry-run/paper/live submit zero orders | P0 |
| E23 | Frozen universe resource missing or checksum-invalid | Block at startup/preview with a resource error | P0 |
| E24 | Provider returns equal scores in different orders | Canonical symbol tie-break yields identical ranking | P1 |
| E25 | Two processes claim one signal or crash around broker access | One locked claim reaches broker at most once; unresolved claim becomes `uncertain` | P0 |
| E26 | Live rank-cache content is modified | Ignore cache, rerank current data, and make zero calls if reranking fails | P0 |

## 6. Security & Permissions

### 6.1 Authentication

Nasdaq snapshot loading requires no credentials. Market-data and broker access
continue using existing KIS/Alpaca environment credentials. The selector never
receives raw credentials or tokens.

### 6.2 Authorization

| Role/surface | Select | Dry-run | Paper order | Live order |
| --- | --- | --- | --- | --- |
| GUI operator | Yes | Yes | Yes with existing settings | No new live command |
| CLI without confirmation | Yes | Yes | Yes | No |
| CLI with all live gates and confirmation | Yes | N/A | N/A | Yes, within the bound envelope |
| Legacy LLM recommendation | Candidate advice only | No direct order | No direct order | No direct order |

### 6.3 Data Protection

- Snapshot and selection cache exclude credentials and account values.
- Persistent session/idempotency state excludes account numbers, balances, and
  credentials; state is scoped conservatively to the local application profile
  so an account change cannot reset daily limits automatically.
- `show-config` masking remains unchanged.
- `.env`, `.kis_token.json`, selection cache, and audit logs remain excluded
  from packaged public artifacts unless explicitly and privately requested.
- Remote StrategySpec code is never executed; only whitelisted schema values
  are parsed.
- Every state-changing live intent must be durably audited before permission;
  an audit failure blocks broker access. Post-order outcomes use a separate
  event so an accepted/rejected response cannot overwrite intent evidence.
- Cached ranks, registry status, and a prior confirmation are never accepted as
  live authorization without a fresh promoted-artifact and spec-digest check.

## 7. Performance & Monitoring

| Metric | Target | Measurement |
| --- | --- | --- |
| KIS selection cycle p95 | <= 60 seconds | elapsed selection audit field |
| Alpaca selection cycle p95 | <= 15 seconds | elapsed selection audit field |
| KIS historical shortlist | <= 30 symbols | report `shortlist_count` |
| Fresh cache response | <= 250 ms | unit/integration timing |
| Duplicate broker orders per cycle | 0 | fake-broker and audit correlation |
| Duplicate live orders across restart | 0 | durable idempotency integration test |
| Selection failure order count | 0 | integration tests and audit |

### 7.1 Monitoring & Alerting

Append structured events to the existing AI Quant audit JSONL:

- `universe_loaded`
- `liquidity_shortlist_created`
- `selection_completed`
- `selection_blocked`
- `selection_cache_used`
- `automatic_order_blocked`
- `automatic_order_submitted`

Each event includes cycle ID, effective date, strategy ID/version, counts,
elapsed milliseconds, selected symbols, and reason codes. It excludes account
balances and secrets. Three consecutive operationally blocked cycles surface a
persistent GUI error until a successful selection occurs. A normal `no_trade`
result is not counted as an error, does not pause the controller, and never
triggers a fallback trade.

## 8. Testing Strategy

### 8.1 Unit Tests

- Strict UniverseSnapshot parsing, symbol normalization, duplicate rejection,
  size bounds, effective date, and staleness.
- June 2026 inclusion/removal fixture.
- Deterministic StrategySpec ranking and threshold/top-N behavior.
- Cache TTL, corrupt cache rejection, and atomic serialization.
- Cache invalidation on registry promotion/rollback, spec digest, mode, universe,
  and market-session changes.
- Held-symbol union logic and no-manual-fallback behavior.
- Per-cycle cash, buying-power, quantity, and exposure reservations across
  multiple accepted buys.
- GUI settings round trip and validation.
- KIS liquidity response parser and ordered intersection.
- KIS Nasdaq exchange-identity normalization and mismatch rejection.
- Equal-score and equal-return permutation tests for canonical symbol ties.
- Live confirmation-envelope market-date, attempt-limit, and binding changes.
- Atomic session-state restore and idempotency-key duplicate suppression.
- Cross-process compare-and-set order claims and crash-window recovery to
  `uncertain` without automatic retry.
- Terminal `rejected` keys suppress a second broker call; reconciliation can
  proceed only with a new signal timestamp/key.

### 8.2 Integration Tests

- Fake KIS ranking -> historical bars -> mode-eligible strategy -> selected symbol ->
  existing rule/risk engine -> DryRunBroker.
- Paper adapter verifies paper base URL and never live base URL.
- Live fake broker proves all existing gates plus a promoted, manually approved
  `CHAMPION` strategy and explicit confirmation are required.
- `TradingEngine` calls the AI Quant readiness/live guard immediately before
  its sole broker path; selector and AI Quant `LiveEngine` broker spies remain
  untouched.
- Live intent-audit failure makes zero broker calls; successful intent and
  outcome events remain separate.
- A cached rank followed by rollback or approval revocation blocks at the
  fresh pre-submit authorization check.
- A modified rank cache cannot choose a live order symbol; live reranks current
  data, and a reranking failure makes zero broker calls.
- Missing strategy, stale universe, missing bars, abnormal spread, insufficient
  cash, and broker rejection each submit zero orders.
- Two simultaneous buy signals cannot reuse the same cycle-start buying power;
  rejected orders do not consume reservations, and sell proceeds are not reused.
- Two concurrent processes claiming the same signal produce exactly one broker
  call. Simulated crashes before/after broker access leave a blocking
  `uncertain` state and never auto-retry without reconciliation.
- Existing held symbol receives a sell evaluation even when not shortlisted.
- CLI `select-symbols` emits JSON and never calls broker submission.
- The packaged EXE finds the bundled universe from its runtime resource path,
  completes a dry-run preview smoke test, and contains no private runtime data.
- A fresh packaged EXE creates an empty writable artifact root and renders
  `학습 완료 전략 없음`; a source-path fixture proves an eligible paper
  artifact can be provisioned without changing the executable.

### 8.3 Edge Case Tests

Every E1-E26 case receives a named Given/When/Then test. The full existing test
suite must remain green. No test may perform a real broker order.

## 9. Rollout Plan

### 9.1 Migration Strategy

No database migration. `auto_symbol_selection_enabled` defaults to `false`, so
existing `trading_config.json` files retain manual ticker behavior. Loading and
saving settings adds the new boolean without rewriting unrelated values. First
run creates empty external artifact and atomic session-state directories; it
does not copy or promote a strategy and does not reset existing daily limits.

### 9.2 Feature Flag

Rollout stages:

1. Flag off by default; ship read-only `select-symbols` preview.
2. Enable GUI dry-run and collect at least 20 successful cycles.
3. Enable paper mode after zero selection-related order-gate violations.
4. Live remains CLI-only and requires the pre-existing live flags, a promoted
   and manually approved `CHAMPION` strategy, and explicit
   `--confirm-live-orders`. A live loop additionally requires the separately
   issued market-date authorization and blocks after 12 actual order attempts
   or any session/binding mismatch.

### 9.3 Rollback Plan

- Set `auto_symbol_selection_enabled=false` to restore manual behavior.
- Set AI Quant strategy registry to rollback/no-trade to block learned
  selection.
- Set app mode to `dry_run` and `allow_live_trading=false` to block live orders.
- Preserve the durable session/idempotency ledger during rollback so previously
  submitted signals and daily limits cannot be forgotten.
- Revert the feature files while retaining backward-compatible config parsing.

## 10. Dependencies & Risks

### 10.1 Dependencies

| Dependency | Owner | Status | Risk if Delayed |
| --- | --- | --- | --- |
| Nasdaq-100 methodology and change notices | Nasdaq | Available | Snapshot cannot be authoritatively updated |
| KIS overseas ranking, price, bars, quote, account, order APIs | KIS | Available; rate limited | KIS shortlist or execution blocks |
| StrategySpec registry and promotion state | AI Quant Lab | Existing | Auto selection blocks |
| Existing TechnicalStrategy/RiskManager/order gates | Trader core | Existing | No safe final order path |
| Persistent session/idempotency store | Trader core | New | Restart can lose order limits |
| Tk GUI, PyInstaller spec, and build script | Local runtime | Existing; data bundling new | Desktop/EXE delivery unavailable |

### 10.2 Risks

| Risk | Probability | Impact | Mitigation |
| --- | --- | --- | --- |
| Strategy overfitting | Medium | High | Require promoted validation, paper stage, and no online fitting. |
| Stale constituent snapshot | Medium | Medium | Source metadata, 120-day live block, release checklist. |
| KIS rate limit | High | Medium | Max-30 shortlist, bounded retry, fresh cache. |
| Survivorship bias in backtests | Medium | High | Record snapshot effective date; do not claim point-in-time historical membership. |
| Selection concentration | Medium | High | Existing single-position/total-exposure caps and StrategySpec top-N. |
| Auto-selection hides exit symbols | Medium | High | Always union current holdings into evaluation symbols. |
| Multiple candidates reuse one account balance | Medium | Critical | Reserve accepted buy notional, quantity, and exposure within the cycle; do not reuse same-cycle sell proceeds. |
| KIS exchange-code mismatch | Low | Critical | Validate one Nasdaq exchange identity across price, account, and order calls before ranking. |
| Cached rank outlives strategy approval | Medium | Critical | Treat cache as data only; reread promotion/spec digest before every live order. |
| One live confirmation authorizes changing symbols indefinitely | Medium | Critical | Bind authorization to strategy/universe/risk/mode/broker, one market date, and a maximum of 12 actual order attempts. |
| Process restart loses limits or repeats a signal | Medium | Critical | Atomic cross-cycle session ledger and durable idempotency keys. |
| Concurrent processes or crash window duplicate an order | Low | Critical | Inter-process lock, persisted `submitting` claim, conservative `uncertain` recovery, and broker reconciliation. |
| Modified selection cache changes a live symbol | Low | Critical | Never use persisted rank/selection cache in live; rerank current data. |
| Audit storage unavailable | Low | Critical | Require successful intent append before live broker access. |
| Fresh EXE lacks learned artifacts | High | Medium | External writable artifact root, explicit readiness block, and documented research/promotion workflow. |
| LLM prompt creates order | Low | Critical | Keep legacy direct-order block and use typed deterministic StrategySpec only. |
| GUI accidentally arms live | Low | Critical | No new GUI live command; live stays explicitly confirmed CLI-only. |
| API schema drift | Medium | High | Typed parser rejects unknown/malformed response and fails closed. |

## 11. Success Metrics

| Metric | Baseline | Target | Measurement Method |
| --- | --- | --- | --- |
| Manual ticker dependency in auto mode | Required | 0 reads for entry selection | unit spy/assertion |
| Automatic universe breadth | User list, usually 1-5 | Current Nasdaq-100 snapshot | selection report |
| Ranked shortlist | None | <= 30, deterministic | integration fixture |
| Orders on selection failure | Not applicable | 0 | fake broker count |
| Same-cycle buying-power reuse | Possible in a naive multi-symbol loop | 0 | reservation integration test |
| Duplicate orders after restart/cache reuse | Possible with in-memory state | 0 | restart/idempotency integration test |
| Live orders after approval rollback | Possible with naive cache reuse | 0 | pre-submit authorization test |
| Held-position exit coverage | Manual symbols only | 100% held symbols evaluated | integration test |
| Operator explanation | Manual ticker only | symbol, score, reasons, strategy, universe date | GUI/CLI QA |
| Existing regression suite | 212 passing | all existing + new tests pass | unittest discovery |

## 12. Open Questions

No unresolved owner decisions. Defaults approved on 2026-07-10:

- Nasdaq-100 universe.
- Mode-eligible validated StrategySpec ranking rather than new online ML; live
  additionally requires a promoted, manually approved `CHAMPION`.
- Dry-run/paper first.
- Existing explicit live gates retained.
- Live automatic loops use the explicitly issued one-market-date authorization
  with a maximum of 12 actual order attempts defined by
  `PRD-session-scoped-live-authorization.md`.
- Learned artifacts live in an external writable application-data directory;
  no live-approved strategy ships in the EXE.
- No new GUI live-order command.
