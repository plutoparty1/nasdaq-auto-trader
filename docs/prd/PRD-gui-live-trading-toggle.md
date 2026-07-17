# PRD: GUI live trading toggle

**Version**: 0.1
**Date**: 2026-07-16
**Status**: Done
**Size**: M

## 1. Problem Statement

The desktop settings already expose `live_trading`, but the controller rejects every
GUI action when that setting selects `live`. The packaged application therefore cannot
use its own documented live-trading setting.

## 2. Goals & Non-Goals

### Goals

- Allow `dry_run=false` and `live_trading=true` to open the desktop LIVE execution path.
- Treat the saved LIVE setting plus the user's Start action as the desktop order confirmation.
- Keep environment authorization, broker credentials, regular-hours, deposited-cash,
  buying-power, no-short, position, daily-limit, and automatic-strategy gates unchanged.
- Keep `dry_run=true` dominant even when `live_trading=true` is also saved.

### Non-Goals

- Bypassing `NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES` or broker credential validation.
- Submitting a real order during tests or QA.
- Changing strategy signals, risk sizing, or cash-only enforcement.

## 3. User Story & Acceptance Criteria

As the desktop operator, I want to enable or disable live trading in Settings so that
the same EXE can switch safely between dry-run, paper, and live operation.

- AC-1: Given LIVE is selected and environment authorization is valid, when the
  controller creates the engine, then it reaches the live-capable factory with explicit
  live-order confirmation.
- AC-2: Given LIVE is selected but environment authorization or credentials are missing,
  when the operator starts automation, then validation fails immediately and the
  controller remains stopped before any broker client or order is created.
- AC-3: Given dry-run is enabled, when settings are applied, then LIVE remains disabled.
- AC-4: The desktop banner reports LIVE as enabled with safety gates, not globally blocked.
- AC-5: Existing deposited-cash, buying-power, no-short, market-hours, and order-limit
  tests remain green.

## 4. Technical Design

- Remove only the controller's unconditional `gui_live_trading_disabled` gate.
- Pass `live_order_confirmation=true` only when the resolved GUI config mode is `live`.
- Preserve compatibility with test/custom factories by passing optional constructor
  arguments only when their callable signature accepts them.
- Update the desktop mode banner and operator documentation.
- No API, schema, or credential-storage changes.

## 5. Edge Cases & Error Handling

| Scenario | Expected behavior |
|---|---|
| LIVE on and dry-run on | Dry-run wins; no live broker is selected. |
| LIVE on without environment authorization | `validate_trading_mode` fails closed. |
| LIVE on without credentials | `validate_trading_mode` fails closed. |
| Buy exceeds deposited cash | Existing risk/broker cash gates block it. |
| Sell exceeds position | Existing no-short gate blocks it. |
| Automatic selection is not production-eligible | Existing automatic preflight/authorization gate blocks it. |

## 8. Testing Strategy

- Red/green controller test proving the live-capable factory is reached with confirmation.
- Regression test proving dry-run still overrides the LIVE switch.
- Render test for the LIVE banner.
- Full unit suite, package audit, EXE build, and no-order startup smoke test.
