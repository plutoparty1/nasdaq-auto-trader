from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from .ai_quant_lab.artifact_paths import default_strategy_artifact_paths
from .automatic_selection import AutomaticSelectionRequest
from .automatic_selection_production import prepare_production_automatic_selection
from .cli_types import CliCommandError, CliResult
from .day_trade import (
    DEFAULT_DAY_TRADE_CANDIDATES,
    DayTradeTestConfig,
    DayTradeTestPlanner,
    OrderRecordStore,
)
from .engine import TradingEngine
from .engine_clients import build_default_client, use_offline_dry_run_data
from .dry_run_market_data import DryRunMarketData
from .quant_data.symbol_selector import SelectionReport
from .sell_monitor import HiveSellMonitor, HiveSellMonitorConfig, SellMonitorLog
from .trading_agents import TradingAgentsAdvisor, TradingAgentsConfig


def _run_select_symbols(config) -> SelectionReport:
    market_data = (
        DryRunMarketData()
        if use_offline_dry_run_data(config)
        else build_default_client(config)
    )
    return prepare_production_automatic_selection(
        AutomaticSelectionRequest(
            config,
            market_data,
            default_strategy_artifact_paths(),
            datetime.now(timezone.utc),
        )
    ).report


def _run_day_trade_test(config, args) -> CliResult:
    """Build a same-day one-share buy/sell plan and optionally submit a guarded buy."""

    if config.broker != "kis":
        raise CliCommandError("day-test command requires broker=kis")
    if args.live_trading and args.dry_run:
        raise CliCommandError("--live-trading and --dry-run cannot be used together")
    if not 0 <= args.confirmation_price_tolerance_pct <= 2:
        raise CliCommandError(
            "--confirmation-price-tolerance-pct must be between 0 and 2"
        )

    live_trading = bool(
        args.live_trading or (config.mode == "live" and not args.dry_run)
    )
    if live_trading:
        if config.mode != "live":
            raise CliCommandError("guarded live day-test requires config mode=live")
        if not config.allow_live_trading:
            raise CliCommandError(
                "guarded live day-test requires allow_live_trading=true"
            )
        if config.kis.paper:
            raise CliCommandError("guarded live day-test requires kis.paper=false")

    dry_run = not live_trading
    engine = TradingEngine(config)
    planner = DayTradeTestPlanner(
        DayTradeTestConfig(
            max_total_usd=args.max_total_usd,
            take_profit_pct=args.take_profit_pct,
            stop_loss_pct=args.stop_loss_pct,
            max_hold_minutes=args.max_hold_minutes,
            confirmation_price_tolerance_pct=args.confirmation_price_tolerance_pct,
            record_path=Path(args.record_path),
        ),
        record_store=OrderRecordStore(args.record_path),
    )
    candidates = args.candidate or [
        *config.symbols,
        *DEFAULT_DAY_TRADE_CANDIDATES,
    ]
    plan = planner.build_plan(
        engine.market_data,
        candidate_symbols=candidates,
        dry_run=dry_run,
        live_trading=live_trading,
    )
    if live_trading:
        plan["live_submission"] = planner.submit_live_buy_order(
            engine.market_data,
            plan,
            dry_run=dry_run,
            live_trading=live_trading,
        )
    else:
        plan["live_submission"] = None
    return plan


def _run_sell_monitor(config, args) -> CliResult:
    """Run the HIVE-only sell monitor."""

    if config.broker != "kis":
        raise CliCommandError("sell-monitor command requires broker=kis")
    if config.mode != "live" and not args.dry_run:
        raise CliCommandError("live sell-monitor requires config mode=live")
    if not config.allow_live_trading and not args.dry_run:
        raise CliCommandError("live sell-monitor requires allow_live_trading=true")
    if config.kis.paper and not args.dry_run:
        raise CliCommandError("live sell-monitor requires kis.paper=false")

    engine = TradingEngine(config)
    monitor = HiveSellMonitor(
        engine.market_data,
        HiveSellMonitorConfig(
            take_profit_pct=args.take_profit_pct,
            stop_loss_pct=args.stop_loss_pct,
            trailing_stop_pct=args.trailing_stop_pct,
            force_sell_before_close_minutes=args.force_sell_before_close_minutes,
            max_retries=args.max_retries,
            poll_seconds=args.poll_seconds,
            fill_check_seconds=args.fill_check_seconds,
            fill_poll_seconds=args.fill_poll_seconds,
            dry_run=args.dry_run,
            record_path=Path(args.record_path),
            stop_loss_enabled=args.stop_loss_enabled,
            trailing_stop_enabled=args.trailing_stop_enabled,
            force_sell_before_close_enabled=args.force_sell_before_close_enabled,
            max_hold_until_market_close=args.force_sell_before_close_enabled,
        ),
        log=SellMonitorLog(args.record_path),
    )
    return monitor.run(max_loops=args.max_loops)


def _run_trading_agents(config, args) -> CliResult:
    """Run TradingAgents as a no-order advisory analysis."""

    symbol = (args.symbol or config.symbols[0]).upper()
    analysis_date = args.analysis_date or config.trading_agents.analysis_date
    if analysis_date is None:
        analysis_date = time.strftime("%Y-%m-%d")

    ta_config = TradingAgentsConfig(
        enabled=True,
        decision_policy="advisory",
        selected_analysts=args.analyst or config.trading_agents.selected_analysts,
        analysis_date=analysis_date,
        asset_type=args.asset_type or config.trading_agents.asset_type,
        llm_provider=args.llm_provider or config.trading_agents.llm_provider,
        deep_think_llm=args.deep_think_llm or config.trading_agents.deep_think_llm,
        quick_think_llm=args.quick_think_llm or config.trading_agents.quick_think_llm,
        backend_url=args.backend_url or config.trading_agents.backend_url,
        output_language=args.output_language or config.trading_agents.output_language,
        max_debate_rounds=(
            args.max_debate_rounds
            if args.max_debate_rounds is not None
            else config.trading_agents.max_debate_rounds
        ),
        max_risk_discuss_rounds=(
            args.max_risk_discuss_rounds
            if args.max_risk_discuss_rounds is not None
            else config.trading_agents.max_risk_discuss_rounds
        ),
        results_dir=config.trading_agents.results_dir,
        data_cache_dir=config.trading_agents.data_cache_dir,
        memory_log_path=config.trading_agents.memory_log_path,
        checkpoint_enabled=config.trading_agents.checkpoint_enabled,
        debug=bool(args.debug or config.trading_agents.debug),
    )
    result = TradingAgentsAdvisor(ta_config).analyze(
        symbol,
        analysis_date,
        asset_type=ta_config.asset_type,
    )
    result["dry_run"] = True
    result["live_trading"] = False
    result["submitted_order"] = False
    return result
