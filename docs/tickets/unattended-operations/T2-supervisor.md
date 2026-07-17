# T2: 자동 시작·단일 인스턴스·상태 복구

**PRD Ref**: PRD-unattended-operations > US-1, US-2, US-3
**Priority**: P0
**Size**: M
**Status**: Done
**Depends On**: T1

## 1. Objective

GUI 시작 시 저장 설정으로 자동운영을 시작하고, 같은 사용자의 중복 프로세스를 차단하며 복구 가능한 사전점검 장애를 다음 주기에 재검사한다.

## 2. Acceptance Criteria

- [x] 무인 운영을 켠 GUI는 사용자 클릭 없이 컨트롤러를 시작한다.
- [x] 무인 운영을 끈 GUI는 기존 수동 동작을 유지한다.
- [x] 두 번째 GUI 프로세스는 거래 엔진 생성 전에 종료한다.
- [x] 복구 가능 안전정지는 running 상태를 유지하고 다음 주기를 예약한다.
- [x] 무인 실거래 별도 동의가 없으면 자동 시작은 live authorization을 생성하지 않는다.
- [x] 무인 경로에서도 현금·일일 손실·일일 주문 수·보유 수량·신호 claim 게이트를 통과하지 못한 주문은 제출되지 않는다.
- [x] catch-up 학습은 live promotion과 주문을 만들지 않는다.

## 3. TDD Spec (Red Phase)

| # | Test Name | Type | Description | Expected |
|---|-----------|------|-------------|----------|
| 1 | `test_gui_starts_unattended_controller_on_launch` | Integration | 자동 설정 GUI 생성 | running/즉시 cycle |
| 2 | `test_gui_respects_disabled_unattended_mode` | Integration | 비활성 설정 | stopped |
| 3 | `test_single_instance_rejects_second_holder` | Unit | 동일 잠금 두 번 획득 | 두 번째 false |
| 4 | `test_recoverable_safe_halt_keeps_scheduler_running` | Unit | 계좌 사전조회 실패 | 다음 주기 예약 |
| 5 | `test_unattended_start_without_live_consent_has_no_live_authorization` | Integration | LIVE+무인 동의 false | 주문 권한 없음 |
| 6 | `test_unattended_orders_still_obey_cash_and_daily_risk_gates` | Integration | 현금·손실·횟수 경계 | 제출 0건 |
| 7 | `test_unattended_learning_never_promotes_live_or_submits_order` | Integration | catch-up 학습 | live champion 없음/주문 0건 |
| 8 | `test_before_open_runs_missed_learning_before_trade_cycle` | Unit | 전일 학습 미완료 | OFF_HOURS_LEARNING |
| 9 | `test_unattended_orders_still_obey_position_and_signal_claim_gates` | Integration | 보유수량·동일 signal 경계 | 제출 0건 |

## 4. Implementation Guide

| File | Change Type | Description |
|------|------------|-------------|
| `single_instance.py` | Create | 프로세스 생명주기 잠금 |
| `gui_launcher.py` | Modify | GUI 실행에서 잠금 보유 |
| `app_ui.py` | Modify | 무인 자동 시작 초기화 |
| `app_ui_actions.py` | Modify | 자동 시작·주기 작업 |
| `controller_operations.py` | Modify | 복구 가능 안전정지 정책 |

## 5. Edge Cases

- CLI 진단과 조회 명령은 GUI 잠금과 독립적으로 실행 가능해야 한다.
- 프로세스 비정상 종료 시 OS가 잠금을 해제해야 한다.
- `unattended_live_trading_enabled` 기본값은 false이고 설정 창에서 별도 위험 동의로 노출한다.

## 6. Review Checklist

- [x] Red/Green 확인
- [x] 주문 POST 재시도 없음
- [x] 동일 신호 claim 유지
- [x] 전체 회귀 테스트 통과 (457)
