from __future__ import annotations

from dataclasses import replace
from typing import Final

from .ai_quant_lab.types import JsonObject
from .config import AppConfig
from .config_settings import TradingSettings
from .models import AccountSnapshot, TradeDecision
from .production_fees import FeeSchedule, load_fee_schedule
from .production_runtime import ProductionRuntime
from .risk import RiskManager

CANDIDATE_POLICY_ID: Final = "whole-share-risk-budget-v1"


def candidate_configuration(
    config: AppConfig, settings: TradingSettings, fees: FeeSchedule | None = None,
) -> tuple[AppConfig, TradingSettings]:
    cost_pct = 2 * fees.commission_rate if fees is not None else config.risk.estimated_roundtrip_cost_pct
    minimum_cost = 2 * fees.minimum_fee_usd if fees is not None else config.risk.estimated_roundtrip_minimum_cost_usd
    risk = replace(config.risk, integer_quantity_enabled=True, order_qty=None,
                   max_position_qty=None, allow_additional_buy=False,
                   max_position_pct=.30, max_total_exposure_pct=.30, risk_per_trade_pct=.01,
                   min_cash_buffer_pct=.05, min_order_notional=0,
                   max_order_notional=min(config.risk.max_order_notional or 35, 35),
                   estimated_roundtrip_cost_pct=cost_pct,
                   estimated_roundtrip_minimum_cost_usd=minimum_cost,
                   estimated_sell_tax_pct=fees.tax_rate if fees is not None else config.risk.estimated_sell_tax_pct,
                   estimated_cost_source=fees.source if fees is not None else "unverified_planning_assumption;approval_blocked")
    configured = replace(config, risk=risk,
                         strategy=replace(config.strategy, stop_loss_pct=.03))
    selected = replace(settings, integer_quantity_enabled=True, stop_loss_rate=3,
                       allow_additional_buy=False, daily_minimum_buy_enabled=False,
                       daily_forced_order_enabled=False, ai_order_qty_enabled=False)
    return configured, selected


def candidate_runtime(runtime: ProductionRuntime, fees: FeeSchedule | None = None) -> ProductionRuntime:
    config, settings = candidate_configuration(runtime.config, runtime.settings, fees)
    return replace(runtime, config=config, settings=settings)


def candidate_plan(runtime: ProductionRuntime, account: AccountSnapshot) -> JsonObject:
    fees = load_fee_schedule(runtime)
    candidate = candidate_runtime(runtime, fees)
    scenarios = []
    for price in (20.61, 6.0):
        before = TradeDecision("REFERENCE", "buy", 8, price, ["synthetic_signal"],
                               price * runtime.config.strategy.stop_loss_pct)
        after = replace(before, risk_per_share=price * candidate.config.strategy.stop_loss_pct)
        old_order = RiskManager(runtime.config.risk).build_order(before, account, None, price)
        new_order = RiskManager(candidate.config.risk).build_order(after, account, None, price)
        quantity = int(new_order.qty or 0) if new_order is not None else 0
        planned_cost = max(quantity * price * candidate.config.risk.estimated_roundtrip_cost_pct,
                           candidate.config.risk.estimated_roundtrip_minimum_cost_usd) + quantity * price * candidate.config.risk.estimated_sell_tax_pct if quantity else 0
        scenarios.append({"price_usd": price,
                          "before_quantity": old_order.qty if old_order is not None else 0,
                          "candidate_quantity": quantity,
                          "candidate_notional_usd": quantity * price,
                          "candidate_stop_risk_usd": quantity * (after.risk_per_share or 0),
                          "candidate_roundtrip_cost_usd": planned_cost,
                          "candidate_planned_loss_usd": quantity * (after.risk_per_share or 0) + planned_cost,
                          "input_kind": "synthetic_valid_signal;fixed_stop_only;actual_ATR_may_reduce_quantity"})
    return {"policy_id": CANDIDATE_POLICY_ID, "applied_to_current_settings": False,
            "quantity_method": "floor_strictest_cost_inclusive_integer_capacity",
            "before_quantity_method": "integer_risk_budget" if runtime.settings.integer_quantity_enabled else "fixed_quantity",
            "before_order_qty": runtime.settings.order_qty,
            "before_max_position_qty": runtime.settings.max_position_qty,
            "candidate_quantity_method": "cost_inclusive_integer_risk_budget",
            "fee_verification_method": fees.verification_method if fees is not None else "unverified",
            "account_equity_usd": account.equity, "cash_usd": account.cash,
            "buying_power_usd": account.buying_power,
            "before_single_position_cap_usd": account.equity * runtime.config.risk.max_position_pct,
            "candidate_single_position_cap_usd": account.equity * .30,
            "candidate_total_exposure_cap_usd": account.equity * .30,
            "candidate_risk_budget_usd": account.equity * .01,
            "candidate_cash_buffer_usd": account.equity * .05,
            "candidate_max_order_usd": candidate.config.risk.max_order_notional,
            "candidate_stop_loss_pct": .03,
            "fee_confirmed": fees is not None,
            "fee_source": fees.source if fees is not None else "unverified_planning_assumption;approval_blocked",
            "fee_reviewed_at": fees.reviewed_at if fees is not None else "",
            "candidate_roundtrip_cost_pct": candidate.config.risk.estimated_roundtrip_cost_pct,
            "