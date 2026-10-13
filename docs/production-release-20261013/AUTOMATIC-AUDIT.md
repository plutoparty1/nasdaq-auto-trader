# Runtime audit

H1: fixed quantity and the 5% cap suppress otherwise eligible small-account orders. Distinguishing evidence: existing preflight cash $62.91, symbol cap $3.1455, price $20.61; candidate full-engine replay must calculate integer quantities while preserving the original risk budget.

H2: GUI mode state prevents approval/start despite valid future conditions. Distinguishing evidence: user output `stop_operation_before_mode_change`; new prepare flow must stop only its own dry-run internally and must leave other running traders untouched.

H3: source changes can remain absent from the deployed binary. Distinguishing evidence: frozen archive code signatures plus final EXE runtime identity and socket-blocked isolated replay.

Runtime observations: 2026-10-13 23:23:04 KST account cash/equity $62.91, holdings and pending orders zero. 23:24:26 KST CMCSA historic reference price $20.61 yields actual broker per-symbol order funds $62.45. 23:23:15 KST PID 29816 runs the existing deploy-operating executable. No process was stopped. No fee field exists in inspected ledger/account responses; actual account fees remain unknown.

Verification artifacts to retain: source regression logs, frozen source comparison, final EXE isolated replay JSON, passive own-window screenshots, masked read-only evidence. No production environment debug overrides, breakpoints, or temporary network proxies are used.
