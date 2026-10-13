from nasdaq_auto_trader.models import AccountSnapshot, TradeDecision
from nasdaq_auto_trader.risk import RiskConfig, RiskManager


def test_one_share_stop_exceeds_two_percent_budget_even_without_costs() -> None:
    # Given the user-specified account and eight-percent initial stop.
    account = AccountSnapshot(54.0728143546, 54.0728143546, 54.0728143546)
    decision = TradeDecision("CMCSA", "buy", 5, 20.61, ["signal"], 1.6488)
    risk = RiskManager(RiskConfig(max_position_pct=1, order_qty=1,
                                  risk_per_trade_pct=0.02))
    # When sizing the order, then one share is refused.
    assert risk.build_order(decision, account, None, 20.61) is None


def test_estimated_roundtrip_cost_is_part_of_planned_stop_loss() -> None:
    # Given a stop that fits only when expected costs are omitted.
    account = AccountSnapshot(100, 100, 100)
    decision = TradeDecision("CMCSA", "buy", 5, 20, ["signal"], 0.99)
    risk = RiskManager(RiskConfig(max_position_pct=1, order_qty=1,
                                  risk_per_trade_pct=0.01,
                                  estimated_roundtrip_cost_pct=0.005))
    # When the planned loss includes ten cents of costs, then refuse one share.
    assert risk.build_order(decision, account, None, 20) is None
