# T4: CLI·Windows 배포·E2E

**PRD Ref**: US-1 through US-4
**Priority**: P0
**Size**: M
**Status**: Done
**Depends On**: T1, T2, T3

## Objective

패키지 EXE에서 카나리를 승인·실행하고 전용 Windows 감시 작업으로 재시작한다.

## Acceptance Criteria

- GUI와 카나리 역할이 서로를 중복 프로세스로 오인하지 않는다.
- 전용 작업은 같은 카나리 역할을 중복 실행하지 않는다.
- 감시 작업은 승인 생성 명령을 포함하지 않으며 GUI와 카나리 시작 경쟁에서도 broker 실주문 소유자는 하나뿐이다.
- 장 마감 잔존 포지션은 로컬 운영 인계 파일을 만들고 다음 정규장 exit-only로 복구한다.
- 설치본 fixture E2E가 체결·취소·재시작·마감 시나리오를 통과한다.
- 실제 계좌 E2E는 읽기 전용 사전점검까지만 수행한다.
- 읽기 전용 명령은 주문 메서드를 노출하지 않는 GET-only 전송 경계를 사용하고 balance/nccs 이외 endpoint를 거부한다.
- 모든 리뷰 통과 전 승인 파일 또는 실주문이 생성되지 않는다.

## TDD Spec

1. `test_packaged_canary_cli_runs_fixture_e2e`
2. `test_canary_watchdog_matches_only_canary_role`
3. `test_gui_watchdog_ignores_canary_process`
4. `test_read_only_preflight_reports_no_foreign_state`
5. `test_gui_canary_start_race_has_one_broker_submit_owner`
6. `test_rollback_refuses_completion_with_owned_exposure`
7. `test_expired_arm_recovers_owned_position_exit_only_next_session`
8. `test_broker_lease_blocks_gui_automatic_day_test_sell_monitor_and_manual_cli_posts`
9. `test_scheduler_has_no_path_to_issue_or_refresh_arm`
10. `test_real_preflight_transport_rejects_every_post_and_non_allowlisted_endpoint`
11. `test_watchdogs_match_roles_from_deterministic_process_table_fixture`
12. `test_canary_watchdog_launches_exact_role_specific_command_line`
