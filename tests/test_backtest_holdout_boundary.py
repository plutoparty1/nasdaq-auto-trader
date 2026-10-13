import json
from dataclasses import replace

import pytest

from nasdaq_auto_trader.ai_quant_lab.backtest_engine import (
    BacktestEngine,
    BacktestRequest,
)
from nasdaq_auto_trader.ai_quant_lab.strategy_schema_validation import (
    parse_strategy_spec_json,
)
from nasdaq_auto_trader.learning_strategy_template import candidate_payload
from tests.test_learning_runner import _bars


def test_warmup_has_no_positions_or_fills_before_holdout() -> None:
    bars = _bars()
    parsed = parse_strategy_spec_json(json.dumps(candidate_payload(bars)))
    assert parsed.spec is not None
    request = BacktestRequest(parsed.spec, bars, trade_start_index=199)

    result = BacktestEngine().run(request)

    assert result.success
    assert result.trades
    assert result.equity_curve[:200] == (request.initial_cash,) * 200
    assert min(trade.timestamp for trade in result.trades) >= bars["QQQ"][200].timestamp


@pytest.mark.parametrize("index", [0, -1, 319, 400])
def test_invalid_holdout_boundary_cannot_run(index: int) -> None:
    bars = _bars()
    parsed = parse_strategy_spec_json(json.dumps(candidate_payload(bars)))
    assert parsed.spec is not None
    request = replace(BacktestRequest(parsed.spec, bars), trade_start_index=index)

    result = BacktestEngine().run(request)

    assert not result.success
    assert result.rejection_reasons == ("invalid_trade_start_index",)
