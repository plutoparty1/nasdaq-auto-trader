# T3: 장중 선택·실행 루프

**PRD Ref**: US-2, US-4
**Priority**: P0
**Size**: L
**Status**: Done
**Depends On**: T1, T2

## Objective

저부하 후보 스캔, 1주 진입, ±5% 감시와 마감 청산을 하나의 결정적 루프로 구현한다.

## Acceptance Criteria

- 개장 +15분부터 마감 -30분까지만 진입한다.
- 15초 가격 감시, 60초 포지션 확인과 15분 후보 스캔을 벽시계 주입으로 테스트한다.
- 매수·매도 미체결은 취소 확인 후에만 다음 주문을 허용한다.
- 주문 한도 뒤에도 무주문 스캔 데이터를 마감까지 기록한다.

## TDD Spec

1. `test_entry_is_blocked_outside_entry_window`
2. `test_one_share_buy_uses_fresh_cash_and_buying_power`
3. `test_take_profit_and_stop_loss_trigger_at_five_percent`
4. `test_force_exit_starts_fifteen_minutes_before_close`
5. `test_unfilled_buy_is_cancelled_before_new_candidate`
6. `test_shadow_collection_continues_after_round_trip_cap`
7. `test_cash_boundary_allows_19_50_plus_buffer_and_rejects_20_01`
8. `test_entry_windows_follow_early_close_dst_and_holidays`
9. `test_position_remains_blocks_reentry_and_transitions_exit_only`
10. `test_scan_deep_inspects_at_most_ten_of_top_thirty`
11. `test_get_retry_tick_and_session_budgets_fail_closed_for_entry`
12. `test_audit_log_size_and_retention_are_bounded`
13. `test_scan_stops_at_wall_and_data_budgets_while_owned_position_monitoring_continues_at_bounded_cadence`
14. `test_reconciliation_retry_timeout_never_exceeds_tick_deadline`
