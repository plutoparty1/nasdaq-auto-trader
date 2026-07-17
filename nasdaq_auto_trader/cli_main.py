from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

from .cli_commands_basic import (
    _run_backtest,
    _run_buying_power_check,
    _run_loop,
    _run_once,
)
from .cli_commands_special import (
    _run_day_trade_test,
    _run_select_symbols,
    _run_sell_monitor,
    _run_trading_agents,
)
from .cli_automatic import (
    automatic_live_block,
    automatic_runtime_config,
    print_automatic_block,
)
from .cli_formatters import selection_report_to_dict
from .cli_parser import build_parser
from .cli_types import CliCommandError
from .config import load_config, validate_trading_mode
from .cli_live_canary import run_canary_arm, run_canary_preflight, run_canary_service


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run the requested command."""

    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if getattr(args, "mode", None):
        config = replace(config, mode=args.mode)

    if args.command == "show-config":
        print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "live-canary-preflight":
        result = run_canary_preflight(config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ready"] else 2

    if args.command == "live-canary-arm":
        result = run_canary_arm(config, args.market_date, args.confirm)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "live-canary":
        result = run_canary_service(config, args.max_loops)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"completed", "waiting", "shadow"} else 2

    if args.command == "select-symbols":
        config, _ = automatic_runtime_config(
            config,
            args.trading_config,
            preserve_mode=False,
        )
        validate_trading_mode(config)
        report = _run_select_symbols(config)
        print(json.dumps(selection_report_to_dict(report), ensure_ascii=False, indent=2))
        return 2 if report.status == "blocked" else 0

    if args.command == "gui":
        from .app import launch_gui

        launch_gui(
            config,
            config_path=args.config,
            trade_interval_seconds=args.trade_interval_minutes * 60,
            portfolio_refresh_seconds=args.portfolio_refresh_seconds,
            settings_path=args.trading_config,
        )
        return 0

    if args.command == "backtest":
        result = _run_backtest(config, Path(args.csv), args.cash)
        print(
            json.dumps(
                {
                    "starting_cash": result.starting_cash,
                    "ending_value": round(result.ending_value, 2),
                    "return_pct": round(result.return_pct, 2),
                    "max_drawdown_pct": round(result.max_drawdown_pct, 2),
                    "sharpe_ratio": round(result.sharpe_ratio, 3),
                    "trade_count": result.trade_count,
                    "win_rate": round(result.win_rate, 2),
                    "trades": [asdict(trade) for trade in result.trades],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "once":
        if args.auto_select:
            blocked_reason = automatic_live_block(
                config,
                args.confirm_live_orders,
            )
            if blocked_reason:
                print_automatic_block(blocked_reason)
                return 2
            config, settings = automatic_runtime_config(
                config,
                args.trading_config,
            )
            validate_trading_mode(config)
            result = _run_once(
                config,
                live_order_confirmation=args.confirm_live_orders,
                trading_settings=settings,
                automatic=True,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if result["status"] == "blocked" else 0
        validate_trading_mode(config)
        print(
            json.dumps(
                _run_once(config, live_order_confirmation=args.confirm_live_orders),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "buying-power":
        validate_trading_mode(config)
        print(
            json.dumps(
                _run_buying_power_check(config, args.symbol, args.qty),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "day-test":
        validate_trading_mode(config)
        print(
            json.dumps(
                _run_day_trade_test(config, args),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "sell-monitor":
        validate_trading_mode(config)
        print(
            json.dumps(
                _run_sell_monitor(config, args),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "trading-agents":
        validate_trading_mode(config)
        print(
            json.dumps(
                _run_trading_agents(config, args),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "loop":
        if args.auto_select:
            blocked_reason = automatic_live_block(
                config,
                args.confirm_live_orders,
                args.live_auth_minutes,
                args.live_max_cycles,
                require_envelope=True,
            )
            if blocked_reason:
                print_automatic_block(blocked_reason)
                return 2
            config, settings = automatic_runtime_config(
                config,
                args.trading_config,
            )
            validate_trading_mode(config)
            reason = _run_loop(
                config,
                args.interval_minutes,
                args.max_runs,
                live_order_confirmation=args.confirm_live_orders,
                trading_settings=settings,
                automatic=True,
                live_auth_minutes=args.live_auth_minutes,
                live_max_cycles=args.live_max_cycles,
            )
            return 2 if reason else 0
        validate_trading_mode(config)
        _run_loop(
            config,
            args.interval_minutes,
            args.max_runs,
            live_order_confirmation=args.confirm_live_orders,
        )
        return 0

    raise CliCommandError(f"unknown command: {args.command}")
