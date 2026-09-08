from __future__ import annotations

import json
import time
from math import isfinite
from pathlib import Path
from typing import Literal, overload

from .backtest import Backtester, BacktestResult
from .cli_formatters import _account_to_dict, automatic_cycle_to_dict
from .cli_types import (
    CliCommandError,
    CliResult,
    JsonObject,
    KISBuyingPowerClient,
)
from .config import AppConfig
from .config_manager import TradingSettings
from .data import load_bars_csv
from .engine import TradingEngine, decision_to_dict
from .quant_data.resources import application_data_root
from .risk import RiskManager
from .session_state_persistence import load_session_state, save_session_state
from .strategy import TechnicalStrategy
from .trading_session_store import TradingSessionStore


def _run_backtest(config: AppConfig, csv_path: Path, cash: float) -> BacktestResult:
    """Run a CSV backtest with the configured strategy and risk rules."""

    bars = load_bars_csv(csv_path)
    strategy = TechnicalStrategy(config.strategy)
    risk_manager = RiskManager(config.risk)
    return Backtester(strategy, risk_manager).run(bars, starting_cash=cash)


@overload
def _run_once(
    config: AppConfig,
    live_order_confirmation: bool = False,
    trading_settings: TradingSettings | None = None,
    *,
    automatic: Literal[True],
    engine: TradingEngine | None = None,
) -> JsonObject: ...


@overload
def _run_once(
    config: AppConfig,
    live_order_confirmation: bool = False,
    trading_settings: TradingSettings | None = None,
    automatic: Literal[False] = False,
    engine: TradingEngine | None = None,
) -> list[JsonObject]: ...


def _run_once(
    config: AppConfig,
    live_order_confirmation: bool = False,
    trading_settings: TradingSettings | None = None,
    automatic: bool = False,
    engine: TradingEngine | None = None,
) -> JsonObject | list[JsonObject]:
    """Run one decision cycle and return JSON-safe output."""

    runtime = engine
    session_store: TradingSessionStore | None = None
    if runtime is None and automatic:
        runtime = TradingEngine(
            config,
            live_order_confirmation=live_order_confirmation,
            trading_settings=trading_settings,
        )
    elif runtime is None:
        session_store = TradingSessionStore(
            application_data_root() / "runtime" / "trading_session.json"
        )
        session_state = load_session_state(session_store)
        runtime = TradingEngine(
            config,
            live_order_confirmation=live_order_confirmation,
            trading_session_state=session_state,
        )
    try:
        results = runtime.run_once()
    finally:
        if session_store is not None:
            save_session_state(session_store, runtime.trading_session_state)
    if automatic:
        return automatic_cycle_to_dict(runtime.last_selection_report, results)
    output: list[JsonObject] = []
    for item in results:
        output.append(
            {
                "symbol": item["symbol"],
                "decision": decision_to_dict(item["decision"]),
                "order": item["order"].to_alpaca_payload()
                if item["order"] is not None
                else None,
                "response": item["response"],
                "account": _account_to_dict(item["account"]),
                "buying_power_check": item["buying_power_check"],
                "trading_agents": item["trading_agents"],
                "ai_decision": item.get("ai_decision"),
            }
        )
    return output


def _run_buying_power_check(
    config: AppConfig,
    symbol: str | None,
    qty: float,
) -> CliResult:
    """Check one KIS overseas buying-power scenario without submitting an order."""

    if qty <= 0:
        raise CliCommandError("qty must be greater than zero")
    if config.broker != "kis":
        raise CliCommandError("buying-power command requires broker=kis")

    engine = TradingEngine(config)
    client = engine.market_data
    if not isinstance(client, KISBuyingPowerClient):
        raise CliCommandError(
            "configured market data client does not support KIS psamount"
        )

    target_symbol = (symbol or config.symbols[0]).upper()
    latest_price = client.get_latest_price(target_symbol)
    available_amount = client.get_overseas_buying_power(target_symbol, latest_price)
    required_amount = latest_price * qty
    account = client.get_account()
    positions = client.list_positions()
    position = positions.get(target_symbol)

    return {
        "dry_run": True,
        "submitted_order": False,
        "symbol": target_symbol,
        "qty": qty,
        "latest_price": latest_price,
        "required_amount": round(required_amount, 4),
        "available_amount": available_amount,
        "buying_power_source": "kis_inquire_psamount",
        "buy_possible": min(account.cash, available_amount) >= required_amount,
        "current_position_qty": 0 if position is None else position.qty,
        "sell_possible_without_short": bool(position and position.qty >= qty),
        "account": _account_to_dict(account),
    }


def _run_loop(
    config: AppConfig,
    interval_minutes: float,
    max_runs: int | None,
    live_order_confirmation: bool = False,
    trading_settings: TradingSettings | None = None,
    automatic: bool = False,
) -> str | None:
    """Repeat decision cycles until interrupted or max_runs is reached."""

    if not isfinite(interval_minutes) or interval_minutes <= 0:
        raise CliCommandError(
            "interval-minutes must be a finite number greater than zero"
        )
    if max_runs is not None and max_runs <= 0:
        raise CliCommandError("max-runs must be greater than zero")

    engine = None
    if automatic:
        engine = TradingEngine(
            config,
            live_order_confirmation=live_order_confirmation,
            trading_settings=trading_settings,
        )
    run_count = 0
    while True:
        run_count += 1
        result = _run_once(
            config,
            live_order_confirmation=live_order_confirmation,
            trading_settings=trading_settings,
            automatic=automatic,
            engine=engine,
        )
        print(json.dumps(result, ensure_ascii=False))
        if automatic:
            if not isinstance(result, dict):
                raise CliCommandError("automatic cycle returned invalid output")
            if result.get("status") == "blocked":
                return str(result.get("reason") or _selection_block_reason(result))
        if max_runs is not None and run_count >= max_runs:
            return None
        time.sleep(interval_minutes * 60)

def _selection_block_reason(result: JsonObject) -> str:
    selection = result.get("selection")
    if isinstance(selection, dict):
        reasons = selection.get("blocked_reasons")
        if isinstance(reasons, list) and reasons:
            return str(reasons[0])
    return "selection_blocked"
