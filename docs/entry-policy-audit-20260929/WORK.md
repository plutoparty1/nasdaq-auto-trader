
Plan gap review incorporated: no prompt for discoverable facts; source/EXE static proof, private storage path, bounded auth/query, raw vs simulated fills, partial months, same-risk proxy limitation, no stale price timestamp invention. Existing wider-stop runner left intact; new separate ABC runner owns new modules.

Completed 2026-09-29. User-authorized local implementation/read-only acquisition only; no live submission/cancel/EXE/task run. Final report and commands: REPORT.md / VERIFICATION.md.

Investigation hypotheses and results:
- H1 retired minimum policy: rejected. Current source and static current EXE both retain active daily_minimum; retired daily_forced is separate.
- H2 low-score minimum promotion then held technical signal: reproduced through real engine fake broker at5minutes. Same-data sell signal conflicts with permissive entry.
- H3 fixed5% stop explains three logs: unsupported; recorded general technical reasons, saved current3% mapping verified, historical per-order config missing.
- H4 data unavailable/auth denied: partly rejected. Correct GUI credentials found, KIS22filledorders/11closedcycles plus500daily and4session5min data; public519daily/530FX. Actual execution timestamps/fees absent in responses.

Implemented separate Aminimum proxy, Bno minimum, Cconflict+completed-bar gating; new marks preserve hard exits. No numeric exit or live allocation changes. AllABCcommon1% differs historicalminimum5%override, clearly marked proxy.

Actual evidence: daily mainABCidentical2roundtrips, supplementary removal costsdownbutnetworse,4sessionCconflicts/5mingeneralexitsdownbutstillloss. No target-based tuning, no positive monthly claim. Existing8/10/ATRcandidates preserved.

Resolved independent-review defects: nonemptyoutputoverwrite, rawdate/naivetime normalization, dotenv per-file duplicate precedence, total50%fill-time enforcement. All reviewsPASS. Exact commands/results and limits in VERIFICATION; prior29auditedhashes differonlythe2backtestfiles, runtime10unchanged. FinalRuffclean andcompile0;555tests+29subtests thenchangedcollector28focused notsummed.

Remaining evidentiary limits (not unfinished implementation): noexactoldbinary-eventhash, noactualfilltimes/fees/fullhistoricalselector, nointrabarorderqueue orspinoffrights,4sessionsnotmonthlysample,1%proxydoesnotreconstructminimum5%accountoutcome. No realdeployment authorized/performed.
