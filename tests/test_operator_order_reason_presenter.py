import pytest

from nasdaq_auto_trader.ai_quant_lab.operator_gui_models import OperatorGuiResult
from nasdaq_auto_trader.ai_quant_lab.operator_gui_presenter import (
    gui_result_explanation,
    human_reason,
)


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (
            "automatic_order_reconciliation_required",
            "이전 주문 결과가 확정되지 않아 증권사 주문·체결 내역 대사가 필요함",
        ),
        (
            "automatic_order_submission_in_progress",
            "이전 자동주문을 제출 중이므로 중복 주문을 막기 위해 대기함",
        ),
    ],
)
def test_order_guard_reason_explains_required_action_when_blocked(
    reason: str, expected: str
) -> None:
    # Given an order guard reason, when it is presented to the operator.
    explanation = human_reason(reason)

    # Then the explanation identifies the order state and required action.
    assert explanation == expected


def test_result_explains_reconciliation_when_previous_order_is_unresolved() -> None:
    # Given a blocked automatic order result.
    result = OperatorGuiResult(
        action="live-cycle",
        payload={"blocked_reasons": ["automatic_order_reconciliation_required"]},
        exit_code=2,
        summary="",
    )

    # When the operator result is presented.
    explanation = "\n".join(gui_result_explanation(result))

    # Then the operator can identify the unresolved order and reconciliation need.
    assert "이전 주문 결과가 확정되지 않아" in explanation
    assert "증권사 주문·체결 내역 대사가 필요함" in explanation
