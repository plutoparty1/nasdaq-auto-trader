from nasdaq_auto_trader.app_format import _summarize_trade_result
from nasdaq_auto_trader.exit_diagnostics import ExitDiagnostics, exit_diagnostics
from nasdaq_auto_trader.models import TradeDecision


def test_trade_summary_retains_safe_exit_context() -> None:
    decision = TradeDecision("TEST", "sell", 98, 9.94, ["atr_stop_loss"])
    summary = _summarize_trade_result({
        "symbol": "TEST", "decision": decision,
        "exit_diagnostics": ExitDiagnostics(fixed_stop_price=9.5, atr_stop_price=9.94),
    })
    assert '"fixed_stop_price":9.5' in summary
    assert '"atr_stop_price":9.94' in summary


def test_mark_timestamp_is_unknown_and_config_has_no_credentials() -> None:
    from nasdaq_auto_trader.models import Bar, Position
    from nasdaq_auto_trader.strategy import TechnicalStrategy

    bar = Bar("TEST", "2026-09-28", 10, 10, 10, 10, 100)
    context = exit_diagnostics(TechnicalStrategy(), [bar], Position("TEST", 1, 9.94, 10))
    assert context.decision_price == 9.94
    assert context.price_timestamp is None
    assert context.price_source == "broker_position_market_value_per_share"
    assert context.bar_timestamp == "2026-09-28"
    assert context.atr_value is None
    assert len(context.config_digest) == 16


def test_invalid_atr_diagnostic_is_json_safe_and_retains_fixed_stop() -> None:
    from unittest.mock import patch

    from nasdaq_auto_trader.models import Bar, Position
    from nasdaq_auto_trader.strategy import TechnicalStrategy

    bars = [Bar("TEST", str(i), 10, 10, 10, 10, 100) for i in range(15)]
    with patch("nasdaq_auto_trader.exit_diagnostics.atr", return_value=float("nan")):
        context = exit_diagnostics(TechnicalStrategy(), bars, Position("TEST", 1, 10, 10))
    assert context.atr_value is None
    assert context.fixed_stop_price == 9.299999999999999
    assert 'NaN' not in context.to_json()


def test_legacy_invalid_atr_threshold_is_explicit_in_diagnostics() -> None:
    from nasdaq_auto_trader.models import Bar, Position
    from nasdaq_auto_trader.strategy import TechnicalStrategy

    bars = [Bar("TEST", str(i), 10, 10, 10, 10, 100) for i in range(15)]
    strategy = TechnicalStrategy()
    position = Position("TEST", 1, 10, 10)
    assert strategy.protective_exit("TEST", bars, position).reasons == ["atr_stop_loss"]
    context = exit_diagnostics(strategy, bars, position)
    assert context.atr_stop_price == 10
    assert context.effective_stop_price == 10
    assert context.raw_atr_value == 0
    assert context.atr_status == "invalid_nonpositive_legacy_active"
