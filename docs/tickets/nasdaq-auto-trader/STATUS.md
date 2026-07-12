# Pipeline Status: NASDAQ Auto Trader

**PRD**: docs/prd/PRD-nasdaq-auto-trader.md
**Size**: L
**Current Phase**: 5 continuation

## Ticket Status Definition

- **Todo**: Not started
- **In Progress**: Implementation in progress
- **In Review**: Review in progress
- **Done**: Acceptance criteria met and tests pass
- **Invalidated**: Replaced by a later plan

## Tickets

| Ticket | Title | Status | Review | Notes |
| --- | --- | --- | --- | --- |
| T1 | Research and product specification | Done | PASS | Reference review and PRD created |
| T2 | Quant signal engine | Done | PASS | Added ATR, Donchian, stochastic, ROC, volume, regime |
| T3 | Risk-managed order construction | Done | PASS | Added fixed-fraction risk sizing |
| T4 | Backtest metrics and execution model | Done | PASS | Added next-open execution and metrics |
| T5 | CLI/docs/tests | Done | PASS | README, config, tests, and CLI output updated |
| T6 | AI quant lab fail-closed platform | Done | PASS | Added StrategySpec schema, insane-search-only research boundary, validation/scoring/registry, self-improvement loop, promoted live execution guard, and safety tests |
| T7 | AI quant live integration adapter | Done | PASS | Added disabled-by-default connector from promoted-strategy LiveEngine to existing TradingEngine broker/data clients, with durable audit RiskGuard and integration tests |
| T8 | Paper/shadow feedback core | Done | PASS | Added virtual fills with costs, unsupported-side blocking/failure handling, paper/shadow ledger, minimum-duration readiness gates, and post-trade feedback injection into the next research loop |
| T9 | AI quant operator CLI | Done | PASS | Added fail-closed `python -m nasdaq_auto_trader ai-quant` commands for status, nightly, champion-lock, paper-shadow, and live-cycle workflows |
| T10 | AI quant desktop operator GUI | Done | PASS | Added `python -m nasdaq_auto_trader ai-quant gui` Tk operator window plus headless `--smoke` check for the same fail-closed workflows |
| T11 | Advanced overfit validation evidence | Done | PASS | Replaced blanket advanced-metric placeholders with conservative purged-CV, CPCV consistency, PBO proxy, deflated-Sharpe proxy, and multiple-testing penalty metrics; added `nightly --bars-json` operator input |
| T12 | Configured insane-search runner | Done | PASS | Added fail-closed `ai_quant_config.json` command/timeout fields so unattended nightly runs can use an approved local insane-search adapter without weakening default unavailable behavior |
| T13 | Rollback no-trade operator path | Done | PASS | Added registry and CLI rollback support that rewrites promoted strategy to `status=rollback`, `mode=no_trade`, `allowed_for_live=false`, upserts rollback state, and audits `rollback_triggered` |
| T14 | Automatic degradation monitor rollback | Done | PASS | Added ledger-driven `monitor-degradation` command that rolls back the promoted champion to no-trade on drawdown, daily-loss, missing telemetry, or malformed telemetry breaches |
| T15 | Mandatory strategy-family research coverage | Done | PASS | Nightly StrategySpec research context now queries insane-search evidence for all 13 required whitelisted strategy families, rejects partial/duplicate source evidence, and rejects StrategySpecs citing out-of-context research IDs |
| T16 | 공식 캘린더와 운영 상태 머신 | Done | PASS | NASDAQ 일정, 원자적 상태 복구, 장전·장중·장후·장외 전환과 안전 중지 추가 |
| T17 | 실제 데이터 학습과 실거래 이중 잠금 | Done | PASS | 가짜 부트스트랩 제거, 완료 봉 학습·취소·중복 방지·보고서와 환경 잠금 추가 |

## Review History

| Phase | Round | Verdict | P0 | P1 | P2 | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 1 | ALL PASS | 0 | 0 | 1 | P2: live deployment needs real monitoring outside this local CLI scope |
| 4 | 1 | ALL PASS | 0 | 0 | 1 | P2: no transaction-cost model yet; documented as limit |
| 5 | 1 | PASS | 0 | 0 | 0 | Unit tests pass after risk-cap expectation split |
| 6 | 1 | ALL PASS | 0 | 0 | 2 | P2: no slippage model; no walk-forward optimizer |
| 5 | 2 | PASS | 0 | 0 | 1 | T6 continuation: advanced overfit metrics are explicit non-promotion placeholders |
| 5 | 3 | PASS | 0 | 0 | 1 | T7 continuation: existing-engine adapter added; CLI/GUI default path and paper/shadow feedback remain follow-up scope |
| 5 | 4 | PASS | 0 | 0 | 1 | T8 continuation: paper/shadow core added with unsupported-side blocking; operator workflow continued in T9 |
| 5 | 5 | PASS | 0 | 0 | 1 | T9 continuation: operator CLI added and manually QA'd; desktop GUI workflow remains follow-up scope |
| 5 | 6 | PASS | 0 | 0 | 1 | T10 continuation: desktop operator GUI added; Tk smoke passed, independent visual reviewer/screenshot capture remains unavailable in this harness |
| 5 | 7 | PASS | 0 | 0 | 1 | T11 continuation: advanced overfit metrics are now computed and audited from backtest equity curves; exact institutional CPCV/PBO/DSR formulas remain conservative proxy implementations |
| 5 | 8 | PASS | 0 | 0 | 1 | T12 continuation: nightly can use a configured approved insane-search command; live defaults remain fail-closed and the command must still be supplied by operations |
| 5 | 9 | PASS | 0 | 0 | 1 | T13 continuation: operator rollback now forces promoted strategy to no-trade; automated degradation trigger remains future monitoring scope |
| 5 | 10 | PASS | 0 | 0 | 1 | T14 continuation: ledger-driven degradation monitoring now triggers rollback automatically; external scheduler/alerting remains production operations scope |
| 5 | 11 | PASS | 0 | 0 | 1 | T15 continuation: StrategySpec generation context is now backed by all mandatory strategy-family research queries and candidate citations must bind to that audited context; source quality still depends on the configured approved insane-search adapter |
| 5 | 12 | PASS | 0 | 0 | 1 | T16-T17: 운영 상태와 실제 데이터 학습 경로를 통합했고 전체 373개 테스트를 통과함. 실거래 전 장기 PAPER 검증은 계속 필요함 |
