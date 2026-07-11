from datetime import date, timedelta

from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestResult
from nasdaq_auto_trader.ai_quant_lab.insane_search_research import (
    ResearchResult,
    SourceMetadata,
)
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import validate_strategy_spec
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationResult
from nasdaq_auto_trader.execution.position_sizer import PortfolioState
from nasdaq_auto_trader.execution.risk_guard import MarketHealth
from nasdaq_auto_trader.quant_data.features import PriceBar


class FakeRunner:
    def __init__(self, available=True):
        self.available = available
        self.calls = []

    def is_available(self):
        return self.available

    def run(self, query):
        self.calls.append(query)
        index = len(self.calls)
        return ResearchResult(
            research_id=f"research-{index}",
            provider="insane_search",
            query=query,
            created_at="2026-06-30T00:00:00+09:00",
            sources=(
                SourceMetadata(
                    f"source-{index}",
                    "Walk Forward Validation",
                    "https://example.test/wfv",
                    "2026-01-01",
                    "source summary",
                ),
            ),
            summary="usable research",
            usable=True,
            failure_reason="",
        )


class FakeSpecProvider:
    def __init__(self, specs):
        self.specs = tuple(specs)
        self.calls = 0

    def request_strategy_specs(self, prompt, context):
        self.calls += 1
        return self.specs


class MemorySpecStore:
    def __init__(self, spec):
        self.spec = spec

    def load(self, strategy_id, version):
        if (strategy_id, version) == (self.spec.strategy_id, self.spec.version):
            return self.spec
        return None


class FakeLiveMarketData:
    def __init__(self, bars, portfolio):
        self.bars = bars
        self.portfolio = portfolio

    def latest_bars(self):
        return self.bars

    def market_health(self, symbol):
        return MarketHealth()

    def portfolio_state(self):
        return self.portfolio


class FakeBroker:
    def __init__(self):
        self.orders = []

    def submit_order(self, intent):
        self.orders.append(intent)
        return {"status": "submitted"}


def valid_spec_payload() -> JsonObject:
    return {
        "strategy_id": "auto_generated_strategy_001",
        "version": "v1",
        "strategy_family": "ensemble",
        "description": "test strategy",
        "research_basis": {
            "provider": "insane_search",
            "research_ids": ["research-1"],
            "source_ids": ["source-1"],
            "summary": "research-backed",
        },
        "signals": [
            {"type": "cross_sectional_momentum", "lookback_days": 20, "weight": 0.6},
            {"type": "breakout", "lookback_days": 20, "weight": 0.4},
        ],
        "entry_rule": {"type": "weighted_score", "threshold": 0.1, "top_n": 2},
        "exit_rule": {
            "stop_loss_mode": "atr_multiple",
            "stop_loss_atr_multiple": 2.0,
            "take_profit_mode": "atr_multiple",
            "take_profit_atr_multiple": 3.0,
            "trailing_stop": True,
            "max_holding_days": 10,
        },
        "position_sizing": {
            "method": "volatility_target",
            "risk_per_trade_pct": 0.005,
            "confidence_adjusted": True,
            "max_single_position_pct": 0.05,
        },
        "risk_controls": {
            "use_kill_switch": True,
            "block_if_data_stale": True,
            "block_if_spread_abnormal": True,
            "block_if_daily_loss_limit": True,
            "block_before_market_close": True,
        },
        "metadata": {
            "created_by": "ai_quant_lab",
            "created_at": "2026-06-30T00:00:00+09:00",
        },
    }


def valid_spec():
    validation = validate_strategy_spec(valid_spec_payload())
    if validation.spec is None:
        raise AssertionError(validation.reasons)
    return validation.spec


def bars(symbol="QQQ"):
    output = []
    for index in range(80):
        close = 100 + index
        timestamp = (date(2026, 1, 1) + timedelta(days=index)).isoformat()
        output.append(
            PriceBar(
                symbol,
                timestamp,
                close - 0.5,
                close + 1,
                close - 1,
                close,
                1_000_000 + index,
                bid=close - 0.01,
                ask=close + 0.01,
            )
        )
    return output


def promoted_payload(strategy_id):
    return {
        "active_strategy_id": strategy_id,
        "strategy_version": "v1",
        "status": "champion",
        "mode": "live",
        "allowed_for_live": True,
        "manual_approval": True,
        "research_basis": {
            "provider": "insane_search",
            "research_ids": ["research-1"],
            "source_ids": ["source-1"],
        },
    }


def fake_backtest_result(strategy_id):
    return BacktestResult(
        experiment_id="experiment-1",
        strategy_id=strategy_id,
        success=True,
        metrics={
            "total_return": 0.1,
            "cagr": 0.1,
            "sharpe": 1.0,
            "sortino": 1.0,
            "max_drawdown": 0.05,
            "win_rate": 0.5,
            "profit_factor": 1.5,
            "expectancy": 0.1,
            "turnover": 0.1,
        },
        trades=(),
        equity_curve=tuple([100_000.0 + index for index in range(40)]),
    )


def fake_validation_result():
    return ValidationResult(
        passed=True,
        promotion_eligible=False,
        metrics={
            "oos_score": 0.5,
            "regime_stability_score": 0.5,
            "execution_quality_score": 0.5,
        },
        rejection_reasons=("advanced_overfit_metrics_not_implemented",),
        missing_advanced_metrics=("pbo",),
    )
