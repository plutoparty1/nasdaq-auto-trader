# Production Readiness Review — 2026-07-17

## Verdict

**LIVE NOT APPROVED.** The code and unattended runtime are prepared for deployment, but the account has no manually approved, promoted `CHAMPION` strategy. The installed runtime must remain `dry_run=true` and `live_trading=false` until that independent gate is satisfied.

No real order was submitted or attempted during this review.

## Safety fixes completed

- Unattended live BUY now requires the approved-strategy path even when a fixed symbol is configured.
- Superseded on 2026-08-11: controller engine cycles now share an explicit
  one-NASDAQ-market-date authorization with a maximum of 12 actual order
  attempts; read-only/no-order cycles do not consume it. See
  `prd/PRD-session-scoped-live-authorization.md`.
- The authorization envelope and consumed actual-order-attempt count survive
  watchdog and process restarts and cannot be silently renewed.
- Only the dedicated explicit authorization command can issue a new
  market-date authorization; GUI setting transitions never create authority.
- Existing deposited-cash, no-short, position-size, daily-order, loss, cooldown, environment, and runtime-mode gates remain fail-closed.

## Verification evidence

- Full automated suite: `Ran 463 tests ... OK`.
- Focused authorization and safety suite: 30 tests passed.
- Python compilation, changed-file strict audit, and `git diff --check` passed.
- Independent P0 re-review, final code-quality review, financial-safety review, and installed-artifact QA: PASS.
- Packaged EXE build and both source/installed private-artifact audits passed.
- Installed EXE help, invalid-input, frozen diagnostic, buying-power, and day-test surfaces passed; every order-submission field remained false.
- Scheduled-task double start preserved exactly one responding installed process; a duplicate GUI exited in 1.432 seconds.
- Final EXE SHA-256: `225FE20C7A5C2C0E0A3E47DB57DECD80712D7FB63285A1B510D3C0E88199B2F1`.

## Current go-live blockers

1. No promoted strategy exists with both `manual_approval=true` and `allowed_for_live=true`.
2. Environment live authorization remains intentionally disabled.
3. Runtime remains intentionally in dry-run with live trading disabled.
4. Before the regular session, the latest dry-run candidate scan produced no eligible candidate.
5. The Windows scheduled task uses an interactive user token. It operates while the user remains signed in, including a locked screen, but does not guarantee startup before sign-in after reboot.

These are independent gates. Enabling only the GUI LIVE switch or only the environment authorization must not produce an order.

## Prepared unattended settings

- One-share order and one-share maximum position.
- No additional averaging buy.
- At most one buy and one sell per day.
- Fifteen-minute cooldown and stop-on-order-error.
- Five-minute decision interval with one retry.
- Automatic confirmations disabled only because unattended mode is guarded by the independent strategy, environment, runtime, cash, and risk gates.

The previous local runtime configuration was backed up before these changes. Secrets and account-specific balances are not included in this report or the distribution folder.
