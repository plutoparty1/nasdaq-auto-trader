# Pipeline Status: 무인 자동운영 및 전일 보고

**PRD**: docs/prd/PRD-unattended-operations.md
**Size**: L
**Current Phase**: 7

## Tickets

| Ticket | Title | Status | Review | Notes |
|--------|-------|--------|--------|-------|
| T1 | 무인 운영 설정과 복구 정책 | Done | PASS | 463 tests |
| T2 | 자동 시작·단일 인스턴스·상태 복구 | Done | PASS | 463 tests; durable live authorization; deployed duplicate/restart E2E; Depends: T1 |
| T3 | 구조화 운영 기록과 전일 보고 | Done | PASS | 463 tests; Windows Tk/report QA |
| T4 | Windows 감시 작업과 배포 | Done | PASS | SHA-256 `225FE20C7A5C2C0E0A3E47DB57DECD80712D7FB63285A1B510D3C0E88199B2F1`; exact-path watchdog |

## Review History

| Phase | Round | Verdict | P0 | P1 | P2 | Notes |
|-------|-------|---------|----|----|-----|-------|
| 2 | 1 | REQUEST_CHANGES | 2 | 6 | 2 | live consent, durable ambiguity, report allowlist, scheduler contract |
| 2 | 2 | ALL PASS | 0 | 0 | 1 | explicit gate coverage; one test naming P2 fixed |
| 4 | 1 | ALL PASS | 0 | 0 | 0 | TDD traceability approved with Phase 2 rerun |
| 6 | 1 | REQUEST_CHANGES | 3 | 2 | 1 | outage retry, terminal outcome pause, private env, deployed hash |
| 6 | 2 | LOCAL PASS / 2 INDEPENDENT PASS | 0 | 0 | 0 | 458 tests; deployed E2E; security and installed-QA reviewers passed; three final reviewers hit usage quota and were rechecked locally |
| 7 | 1 | REQUEST_CHANGES | 3 | 0 | 0 | unattended fixed-symbol BUY bypass and authorization renewal across controller/process restart |
| 7 | 2 | CODE PASS / LIVE NOT APPROVED | 0 | 0 | 0 | P0 re-review passed; 463 tests; account lacks a manually approved promoted strategy, so runtime remains dry-run |
