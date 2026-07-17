# T1: 무인 운영 설정과 복구 정책

**PRD Ref**: PRD-unattended-operations > US-1, US-3
**Priority**: P0
**Size**: M
**Status**: Done
**Depends On**: None

## 1. Objective

무인 운영의 저장 설정, 실행 간격과 안전한 재시도/정지 정책을 타입으로 정의한다.

## 2. Acceptance Criteria

- [x] 기존 설정 파일은 새 필드 없이도 기본값으로 로드된다.
- [x] 보고 시각·주기·보존 기간의 잘못된 값은 저장 전에 차단된다.
- [x] 사전조회 실패만 자동 재점검 대상이며 주문 결과 불명은 자동 재개 대상이 아니다.
- [x] POST claim 이후 중단은 재시작 때 uncertain으로 복구되어 동일 신호 재주문을 차단한다.

## 3. TDD Spec (Red Phase)

| # | Test Name | Type | Description | Expected |
|---|-----------|------|-------------|----------|
| 1 | `test_unattended_defaults_are_backward_compatible` | Unit | 기존 JSON 로드 | 기본값 적용 |
| 2 | `test_unattended_schedule_values_are_validated` | Unit | 범위 밖 설정 | 오류 반환 |
| 3 | `test_only_preorder_failures_are_recoverable` | Unit | 실패 사유 분류 | 주문 오류는 false |
| 4 | `test_interrupted_claim_recovers_uncertain_and_blocks_same_signal` | Integration | claim 후 프로세스 중단 모사 | uncertain/재주문 차단 |
| 5 | `test_post_disconnect_remains_single_attempt_in_unattended_mode` | Integration | POST RemoteDisconnected | 1회 호출/terminal pause |

## 4. Implementation Guide

| File | Change Type | Description |
|------|------------|-------------|
| `config_settings.py` | Modify | 무인 운영 필드 |
| `config_validation.py` | Modify | 설정 범위 검사 |
| `settings_window_fields_advanced.py` | Modify | 쉬운 한글 설정 UI |
| `unattended_policy.py` | Create | 복구 정책 |
| `trading_session_store.py` | Existing contract | interrupted claim 복구 계약 재검증 |

Red 실패 후 최소 구현하고 전체 테스트를 실행한다.

## 5. Edge Cases

- 기존 JSON의 알 수 없는 필드는 계속 무시한다.
- 보고 시각은 현지 24시간제로 제한한다.

## 6. Review Checklist

- [x] Red 확인
- [x] Green 확인
- [x] 전체 회귀 테스트 통과 (457)
- [x] 새 파일 250 pure LOC 이하
