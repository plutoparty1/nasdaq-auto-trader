# Four trading review fixes

The four reviewed defects are corrected, rebuilt and running from the deployed executable. The final independent completion review approved the result with no blocking findings; its report is `.omo/evidence/review-fixes-20260920-gate-review.md`.

| Defect | Result |
| --- | --- |
| KIS terminal orders could leave accepted buys locked | Original rejection, full fill, and an exact completed full-remainder cancellation expose terminal evidence. Cancellation/amendment request rows are excluded from position reconciliation. |
| External sells could permanently lock receipts | Later original-order executions explain reduced holdings, including fractional quantities and day rollover. A confirmed terminal buy no longer prevents selling verified remaining shares solely because its earlier holdings snapshot was reduced. |
| Alpaca lacked the required order history | Date-bounded, cursor-paginated history now feeds receipt reconciliation. Partial notional sells remain visible; an active partial notional buy cannot masquerade as a full fill. |
| Unaffordable top-ranked entries displaced feasible ones | Existing learned, configured, and symbol-specific capacity checks run before top-N. Session-wide final guards preserve audit/authorization behavior, and lookup failures leave other buys and ordinary exits available. |

The 50% position cap, 1% per-trade risk, 3% stop-loss setting, fixed one-share quantity, and five-minute unattended operation are preserved. The position cap alone does not guarantee a purchase; signal, cash, stop-loss and risk checks still apply.

## Verification

- Full suite: **1089 passed, 95 subtests passed, 9 existing failures**. The remaining failures are the two broker HTTP-error redaction cases and seven canary-audit secret-redaction cases already present before these repairs.
- PyInstaller build: exit 0. Package privacy audit: no findings.
- Actual frozen executable: help exits 0; invalid arguments exit 2; offline fixture diagnostic exits 0, selects AAPL and submits no orders or network requests.
- Embedded archive contains the four updated reconciliation/eligibility modules. All 235 production source hashes match the build inputs.
- Independent code, security, context and affected offline QA reviews passed. The code reviewer found no blocking findings; the known unrelated redaction failures remain documented.

Evidence: `.omo/evidence/review-fixes-20260920/` and the final QA follow-up in `.omo/evidence/review-fixes-20260921/`.

## Limits

KIS's documented history contract provides no distinct expiry enum. An unknown expiry remains blocked unless authoritative completed cancellation evidence exists. Missing or ambiguous execution evidence continues to block new buys.

No test orders were sent to a real broker. Desktop automation was unavailable because its native pipe could not connect; executable diagnostics, process/window responsiveness and new runtime logs provide the runtime checks. No visual UI inspection is claimed.

## Deployment

Restarted at **2026-09-21 21:05 KST**. Old PID 6080 is gone; new PID **28448** is the only NasdaqAutoTrader process, is responding and owns the `NASDAQ Auto Trader` window at `dist/NasdaqAutoTrader/NasdaqAutoTrader.exe`.

The fresh log records program start, live mode, five-minute unattended operation and a completed first cycle with zero trading results. This proves startup and cycle execution; it is not evidence of a live fill. The runtime settings file hash is unchanged.

Deployed and staged EXE SHA256 both equal `6C70BBB5EEF9C8AD6026E13A5C78F895C9BDCE9FEC658DB37510C2A6886AF2AE`. The prior installation is preserved under `deploy-backups/review-fixes-20260921-210442/NasdaqAutoTrader`.

Evidence: `deployment.json`, `runtime-process.json`, and `startup-markers.txt` in the primary evidence directory.
