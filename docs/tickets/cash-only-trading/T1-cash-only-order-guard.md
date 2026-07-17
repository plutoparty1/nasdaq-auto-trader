# T1: Enforce deposited-cash ceiling on every buy path

## Given / When / Then

- Given cash is lower than buying power, when a fixed-quantity buy is built, then no order is returned.
- Given a KIS account has separate deposit and orderable amounts, when the account snapshot is parsed, then cash uses only the deposit field.
- Given KIS symbol buying power exceeds cash, when the engine sizes a buy, then effective cash remains the lower deposited balance.
- Given a confirmed day-trade plan and refreshed cash below the limit-order value, when submission is attempted, then `submit_order` is never called.

## Implementation

- Add the required-cash check to fixed-quantity risk sizing.
- Preserve deposited cash in KIS effective account snapshots.
- Remove KIS orderable and purchase-total fields from cash parsing.
- Add account refresh support to the guarded day-trade trading client protocol.
- Recheck cash immediately before direct live submission and fail closed on errors/non-finite values.

## Verification

- Targeted red/green unit tests for each boundary.
- Full unittest discovery.
- Compile/import check.
- Manual in-memory runtime scenarios proving zero broker submissions when cash is insufficient.
