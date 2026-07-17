# T1: KIS 주문 조정 API

**PRD Ref**: US-3
**Priority**: P0
**Size**: M
**Status**: Done

## Objective

KIS 미체결·당일 체결 조회와 주문 취소를 타입이 지정된 경계로 추가한다.

## Acceptance Criteria

- 공식 경로·TR ID·필수 필드를 정확히 사용한다.
- 주문번호, 종목, 방향, 주문·체결·미체결 수량을 정규화한다.
- 빈 행과 모호한 응답은 성공으로 추정하지 않는다.
- 취소 POST는 자동 재시도하지 않는다.
- 1주 이외 체결수량과 장후 30분 내 조정 불가 상태는 영구 차단으로 저장한다.
- 잔고·미체결·체결내역은 continuation을 최대 10페이지까지 읽고 반복 key나 부분 오류에서 실패 폐쇄한다.
- 주문번호 없는 POST 결과는 어떤 휴리스틱으로도 채택하지 않고 영구 수동조정 상태로 둔다.

## TDD Spec

1. `test_list_open_orders_parses_kis_nccs_row`
2. `test_list_order_history_parses_filled_row`
3. `test_cancel_order_uses_original_order_number_once`
4. `test_ambiguous_cancel_response_requires_reconciliation`
5. `test_reconciliation_timeout_blocks_all_new_orders`
6. `test_order_numberless_post_is_never_adopted_or_mutated`
7. `test_balance_open_orders_and_history_follow_all_continuation_pages`
8. `test_repeated_or_failed_continuation_page_fails_closed`
9. `test_canary_get_timeout_is_at_most_eight_seconds`
