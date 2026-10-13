from nasdaq_auto_trader.app_format import _summarize_trade_result
from nasdaq_auto_trader.models import TradeDecision
from nasdaq_auto_trader.selection_presenter import selection_reason_label


def test_trade_log_explains_hold_without_order() -> None:
    decision = TradeDecision("WBD", "hold", 0, 27.8, ["below_long_regime"])

    summary = _summarize_trade_result({"symbol": "WBD", "decision": decision})

    assert "below_long_regime" in summary
    assert "action=hold" in summary


def test_entry_ineligibility_reasons_explain_signal_and_capacity() -> None:
    assert "매수 조건" in selection_reason_label("entry_technical_hold:WBD:below_long_regime")
    assert "투자 한도" in selection_reason_label("entry_risk_capacity:WBD")
    assert "매수 가능한 종목" in selection_reason_label("entry_eligibility_no_candidates")
