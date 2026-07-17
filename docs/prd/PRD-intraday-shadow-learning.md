# PRD: Intraday Shadow Scan and Daily Learning

**Version**: 1.0
**Date**: 2026-07-17
**Status**: Done
**Size**: L

## 1. Problem Statement

The automatic operator currently treats a missing validated strategy as a full
market-hours halt, so it cannot gather read-only observations. Off-hours
learning also receives a hard-coded `new_data_available=True`, which can repeat
the same learning job.

## 2. Goals & Non-Goals

### Goals

- During the Nasdaq regular session, repeatedly inspect the Nasdaq-100 universe
  without invoking any broker order method.
- Keep live trading blocked until the existing strategy and risk gates pass.
- Train at most once per completed Nasdaq market date, using completed daily bars.
- Persist observable scan and learning dates across application restarts.

### Non-Goals

- Scanning every Nasdaq-listed security; the packaged, versioned Nasdaq-100
  universe remains the supported universe.
- Promoting a rejected strategy or weakening any live-order gate.
- Intraday model training from incomplete candles.

## 3. User Stories & Acceptance Criteria

### US-1: Safe intraday research

- AC-1.1: Missing strategy during an open session enters a read-only shadow-scan
  state instead of pausing the application.
- AC-1.2: The scan uses the provider liquidity shortlist (maximum 30 for KIS),
  writes a report, and submits zero orders.
- AC-1.3: Preflight health failures still safe-halt; a runtime market-data failure
  in the scanner also safe-halts and never reaches an order path.

### US-2: Once-per-market-day learning

- AC-2.1: Learning is eligible only when the latest completed market date differs
  from the persisted successful learning date.
- AC-2.2: A completed run records that date; blocked or failed runs remain retryable.
- AC-2.3: Restarting the app does not repeat a completed market-day job.

### US-3: Operator feedback

- AC-3.1: The GUI reports scan count, eligible count, report path, and confirms
  zero submitted orders.
- AC-3.2: Existing live-trading status and cash-only controls remain unchanged.

## 4. Technical Design

### Architecture

`AutomationCoordinator` distinguishes `INTRADAY_SHADOW_SCAN` from
`LIVE_TRADING`. A new read-only scanner accepts only market-data capabilities,
loads the packaged Nasdaq-100 universe, shortlists liquidity, checks completed
daily history and quotes, and atomically saves a report under application data.
`RuntimeState` stores `last_learning_market_date`; the controller derives actual
data availability from the Nasdaq calendar and writes the date only when
`LearningRunResult.status == "completed"`. Blocked, failed, and cancelled runs do
not write it and remain retryable.

### Key Decisions

| Decision | Chosen | Rationale |
|---|---|---|
| Open session without model | Shadow scan | Research remains useful while orders remain impossible |
| KIS universe query | One ranking request + max 30 symbols | Bounded API load and existing provider contract |
| Training data | Completed daily bars only | Avoid look-ahead and partial-candle contamination |
| Idempotency | Persist completed market date | Survives restart and prevents duplicate training |

## 5. Edge Cases & Error Handling

| Scenario | Expected behavior |
|---|---|
| Empty shortlist | Save completed zero-candidate scan; no order |
| Market-data request fails | Preserve trading safety and expose scan failure |
| Corrupt runtime state | Existing explicit corruption error remains |
| Learning blocked/cancelled | Do not mark the market date complete |
| Holiday/weekend | Use the latest calendar session that has closed |

## 6. Security & Permissions

The scanner has no broker/order dependency and receives only a market-data
protocol. No credential or `.env` value is written to reports. Existing live
confirmation, cash-only, no-short, and strategy-promotion gates are unchanged.

## 7. Performance & Monitoring

- KIS shortlist is capped at 30 symbols per scan.
- Scans run at the configured automatic interval, never concurrently.
- Atomic JSON reports at
  `%LOCALAPPDATA%/NasdaqAutoTrader/runtime/intraday_shadow_scan.json` expose
  timestamps, counts, symbols, rejection reasons, and `submitted_order=false`.

## 8. Testing Strategy

- Unit: state transitions, calendar date derivation, state serialization.
- Integration: scanner with a fake market-data adapter and persisted report.
- Controller/E2E: open-market missing-model cycle scans without calling an order;
  post-close learning runs once across restart-equivalent cycles.

## 9. Rollout and Rollback

The state file is backward-compatible through a default empty learning date.
Rollback consists of restoring the previous coordinator/controller and ignoring
the additive state/report fields.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Provider throttling | Existing KIS ranking endpoint and maximum 30 shortlist |
| Research path accidentally trades | Market-data-only protocol plus order-spy test |
| Same-day repeated training | Persist success marker only after completed result |

## 11. Success Metrics

- Open-market missing-model cycles produce a scan report and zero orders.
- A completed market date is learned no more than once.
- Full regression suite and frozen executable smoke test pass.

## 12. Open Questions

None. The user explicitly requested implementation, build, execution, and a
learning run.
