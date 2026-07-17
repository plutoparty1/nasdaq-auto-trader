# PRD: Cash-only live trading guard

## Goal

Every application-managed buy order must be limited by the account's deposited cash balance, even when broker buying power is higher because of margin, unsettled reuse, or exchange-specific order capacity.

## Scope

- Fixed-quantity and notional buys created by `RiskManager`.
- KIS account parsing and KIS symbol-specific order sizing.
- The guarded one-share day-trade live submission path.
- Fail closed when a trustworthy deposited-cash field cannot be read.

## Non-goals

- Placing or simulating an order against a real broker account.
- Changing sell sizing, strategy signals, or live authorization policy.
- Treating broker buying power as deposited cash.

## Acceptance criteria

1. A buy is blocked when required order value exceeds cash, even if buying power covers it.
2. A buy is allowed only when both cash and broker buying power cover it.
3. KIS `frcr_dncl_amt_2`/`frcr_dncl_amt` are treated as cash; orderable-amount fields are not cash fallbacks.
4. KIS symbol-specific sizing preserves the lower real-cash ceiling.
5. Day-trade live submission refreshes the account and rechecks cash immediately before calling `submit_order`.
6. Missing or invalid cash data blocks the buy.
7. Existing sell behavior and dry-run/live authorization guards remain unchanged.

## Safety invariant

For every submitted buy, `estimated_order_value <= max(deposited_cash, 0)` and the broker's buying-power check must also pass. No order is submitted during verification.
