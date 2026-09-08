# Pipeline Status: Daily Minimum One-Share Order

**PRD**: `docs/prd/PRD-daily-minimum-one-share-order.md`  
**Size**: L  
**Current Phase**: 3

## Ticket Status 정의

- **Todo**: 미착수
- **In Progress**: 구현 중
- **In Review**: 리뷰 진행 중
- **Done**: AC 충족 + 테스트 PASS
- **Invalidated**: 상위 계약 변경으로 무효화

## Tickets

| Ticket | Title | Status | Review | Notes |
|---|---|---|---|---|
| T1 | Durable state, authorization, account binding | Todo | - | Foundation |
| T2 | Candidate, timing, and quote policy | Todo | - | Depends: T1 |
| T3 | Ownership reconciliation and admin recovery | Todo | - | Depends: T1 |
| T4 | Guarded engine coordinator and operator feedback | Todo | - | Depends: T1, T2, T3 |
| T5 | Frozen safety, packaging, and rollout evidence | Todo | - | Depends: T4 |

## Review History

| Phase | Round | Verdict | P0 | P1 | P2 | Notes |
|---|---:|---|---:|---:|---:|---|
| 2 | 1 | HAS ISSUE | 0 | 4+ | 3+ | atomicity/state/ownership/frozen proof |
| 2 | 2 | HAS ISSUE | 0 | 4 | 2 | intermediate state/global gate/migrations |
| 2 | 3 | ALL PASS | 0 | 0 | 0-2 | final BOOMER verification P0/P1/P2=0 |

