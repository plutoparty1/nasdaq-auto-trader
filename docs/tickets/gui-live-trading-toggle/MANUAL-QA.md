# Manual QA: GUI LIVE settings

Date: 2026-07-16

No real broker order was submitted or attempted during QA.

| Priority | Scenario | Expected | Result | Evidence |
|---|---|---|---|---|
| P0 | LIVE on, dry-run off | Controller reaches a compatible engine with `live_order_confirmation=True`. | PASS | `tests.test_gui_live_mode.GuiLiveModeTests.test_gui_live_action_reaches_confirmed_engine_factory` |
| P0 | LIVE on without environment approval | Start fails immediately and controller remains stopped. | PASS | `test_gui_live_real_engine_requires_environment_authorization` |
| P0 | LIVE and dry-run both on | Dry-run wins and no live confirmation is granted. | PASS | `test_gui_dry_run_does_not_confirm_live_orders` |
| P0 | Buy exceeds deposited cash | KIS and Alpaca block before an order POST even if buying power is higher. | PASS | `tests.test_broker_cash_guard` |
| P0 | Sell exceeds position | Existing no-short/order-size tests block the sell. | PASS | Full `unittest` regression suite |
| P0 | Final packaged EXE diagnostic | No order and no network client construction. | PASS | Packaged diagnostic: `submitted_order=false`, `network_client_constructed=false` |
| P0 | Final packaged EXE startup | Process stays alive without an early crash. | PASS | 8-second hidden startup smoke, 96.4 MB working set |
| P1 | Package contains no secrets | `.env`, tokens, logs, and runtime settings are absent. | PASS | Package audit `[]`; `env_present=false` |
| P1 | LIVE banner rendering | Banner reports guarded LIVE instead of blanket blocking. | PASS | `test_live_banner_reports_guarded_live_mode` |
| P1 | Windows screenshot and Settings click-through | Korean text is visible without clipping and toggle interaction is observed. | UNAVAILABLE | Windows Computer Use native pipe was unavailable; no foreground automation fallback used. |

## Verification summary

- Full suite: `Ran 458 tests ... OK`
- Strict Python audit: `no violations in 79 file(s)`
- PyInstaller build: exit 0
- Package audit: `[]`
- Final EXE SHA-256: `23128F6FEEB3E935D9F6069069D5E792FAE23679D31FFE75FD0C87D4ECEC21C0`

The remaining screenshot limitation affects visual confirmation only. The settings-to-engine
behavior, fail-closed boundaries, package integrity, and executable startup were exercised.
