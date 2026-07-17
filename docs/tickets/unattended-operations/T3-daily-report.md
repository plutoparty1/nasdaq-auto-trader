# T3: 구조화 운영 기록과 전일 보고

**PRD Ref**: PRD-unattended-operations > US-4
**Priority**: P1
**Size**: M
**Status**: Done
**Depends On**: T2

## 1. Objective

무인 실행 결과를 민감정보 없이 기록하고 최근 완료 거래일 보고서를 오전에 한 번 생성해 GUI에서 열 수 있게 한다.

## 2. Acceptance Criteria

- [x] 상태 전환·학습·거래 주기 결과가 JSONL에 기록된다.
- [x] 보고서는 거래일당 한 파일만 생성된다.
- [x] 손상된 JSONL 행은 누락 경고로 처리하고 보고 생성을 계속한다.
- [x] 최신 보고서 경로와 핵심 요약이 GUI 로그에 표시된다.

## 3. TDD Spec (Red Phase)

| # | Test Name | Type | Description | Expected |
|---|-----------|------|-------------|----------|
| 1 | `test_report_is_due_once_after_local_morning_cutoff` | Unit | 시각과 기존 파일 | 정확한 due 판정 |
| 2 | `test_report_summarizes_runtime_and_order_audits` | Unit | 고정 JSONL fixture | 수치·사유 포함 |
| 3 | `test_report_survives_corrupt_audit_line` | Unit | 깨진 행 포함 | 부분 보고+경고 |
| 4 | `test_gui_renders_daily_report_result` | Integration | report 결과 큐 | 상태·경로 로그 |
| 5 | `test_report_uses_latest_completed_nasdaq_day_across_weekend_holiday_and_dst` | Unit | KST 오전/미국 일정 경계 | 올바른 거래일 |
| 6 | `test_report_allowlist_rejects_secret_shaped_payload_fields` | Security | token/account/cookie payload | 보고서 미포함 |

## 4. Implementation Guide

| File | Change Type | Description |
|------|------------|-------------|
| `runtime_journal.py` | Create | 내구 JSONL 운영 이벤트 |
| `daily_report.py` | Create | 보고 집계·원자적 Markdown 저장 |
| `app_ui_actions.py` | Modify | 보고 생성·열기 |
| `app_ui_render.py` | Modify | 한글 결과 표시 |
| `app_ui_layout.py` | Modify | 최신 보고서 버튼 |
| `controller_operations.py` | Modify | 상태 전환·학습 결과 이벤트 생산 |
| `app_controller.py` | Modify | 거래 주기·계좌 스냅샷 이벤트 생산 |
| `automatic_order_audit.py` | Existing producer | 제출·차단 집계의 감사 이벤트 원천 |

## 5. Edge Cases

- 계좌 스냅샷이 없으면 `확인 불가`로 적고 보고서는 생성한다.
- 감사 로그는 `event_type`, `timestamp`, 알려진 `reason`, 개수 필드만 allowlist로 읽는다. 자격증명·계좌 식별자·원시 응답·알 수 없는 payload는 보고서에 복사하지 않는다.

## 6. Review Checklist

- [x] Red/Green 확인
- [x] 보고서에 비밀정보 없음
- [x] 파일 쓰기 원자적
- [x] 전체 회귀 테스트 통과
