# T2: 승인·상태·위험 상태기계

**PRD Ref**: US-1, US-2, US-3
**Priority**: P0
**Size**: L
**Status**: Done
**Depends On**: T1

## Objective

하루 승인, 실행 파일 바인딩, 역할 잠금과 재시작 가능한 주문 상태를 구현한다.

## Acceptance Criteria

- 최대 20 USD·1주·1포지션·3왕복을 느슨하게 설정할 수 없다.
- 승인 발급은 계좌 지문·실전환경·실행파일·정책·SID·시장일·nonce에 바인딩되고 자동 작업에서 호출할 수 없다.
- 현재 사용자와 SYSTEM 전용 ACL을 적용하지 못하면 승인과 실행을 차단한다.
- 카나리가 계좌별 broker lease를 보유하는 동안 다른 KIS 실주문 경로를 차단한다.
- POST 전에 의도가 내구성 있게 기록된다.
- 결과 불명·상태 손상·외부 포지션은 신규 주문을 차단한다.
- 재시작은 미체결·포지션·체결내역과 저장 상태를 조정한다.
- 승인 만료 후에는 확인된 소유 포지션의 같은 종목·1주 이하 매도만 허용하는 별도 EXIT_ONLY 상태로 전환한다.
- write/fsync/replace 실패와 schema 손상은 POST 전에 실패하고 원시 응답·계좌정보는 상태/감사에 남지 않는다.

## TDD Spec

1. `test_arm_rejects_expired_or_binary_mismatched_envelope`
2. `test_second_process_cannot_acquire_canary_role_lock`
3. `test_restart_after_submit_does_not_duplicate_order`
4. `test_foreign_position_or_order_blocks_entry`
5. `test_round_trip_limit_remains_consumed_after_restart`
6. `test_canary_lease_blocks_gui_and_legacy_kis_submissions`
7. `test_arm_nonce_cannot_bind_to_second_state_file`
8. `test_arm_fails_closed_when_private_acl_cannot_be_applied`
9. `test_authenticated_account_product_and_real_base_url_must_match_arm`
10. `test_expired_arm_exit_only_state_rejects_every_buy`
11. `test_state_write_fsync_replace_failures_prevent_post`
12. `test_state_schema_and_redaction_fail_closed`
13. `test_intent_is_durable_before_transport_post`
14. `test_restart_matrix_never_duplicates_post_or_reopens_entry`
15. `test_next_session_exit_only_resets_sell_attempts_but_never_buy_authority`

Restart matrix는 `intent_before_post`, `order_numberless_buy_post`, `pending_buy`, `cancel_intent`, `order_numberless_cancel_post`, `pending_exit`, `order_numberless_exit`, `post_close_timeout`, `next_session_exit_only`를 각각 독립 fixture로 포함한다. 주문번호 없는 상태는 broker 주문을 절대 변경하지 않는다.
