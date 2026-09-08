from __future__ import annotations

import argparse
from math import isfinite

from .quant_data.resources import application_data_root
from .cli_session_parser import add_live_session_commands


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the command parser."""

    parser = argparse.ArgumentParser(
        prog="nasdaq-auto-trader",
        description="NASDAQ rule-based auto trading helper",
    )
    parser.add_argument("--config", help="Path to a JSON configuration file")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show-config", help="Print effective configuration as JSON")

    add_live_session_commands(subparsers)

    preview = subparsers.add_parser(
        "select-symbols",
        help="Preview learned symbol selection without constructing orders",
    )
    preview.add_argument(
        "--trading-config",
        default="trading_config.json",
        help="Path to automatic trading settings JSON",
    )

    gui = subparsers.add_parser("gui", help="Launch the desktop management app")
    gui.add_argument(
        "--trade-interval-minutes",
        type=float,
        default=60.0,
        help="Automatic trading cycle interval used by the GUI",
    )
    gui.add_argument(
        "--portfolio-refresh-seconds",
        type=float,
        default=15.0,
        help="Holdings refresh interval used by the GUI",
    )
    gui.add_argument(
        "--trading-config",
        default="trading_config.json",
        help="Path to GUI trading settings JSON",
    )

    backtest = subparsers.add_parser("backtest", help="Run a CSV historical backtest")
    backtest.add_argument("--csv", required=True, help="Path to OHLCV CSV bars")
    backtest.add_argument(
        "--cash",
        type=_positive_float,
        default=10_000,
        help="Starting cash",
    )

    once = subparsers.add_parser("once", help="Run one live decision cycle")
    once.add_argument(
        "--mode",
        choices=["dry_run", "paper", "live"],
        help="Temporarily override config mode",
    )
    once.add_argument(
        "--confirm-live-orders",
        action="store_true",
        help="Final explicit confirmation required before legacy live order submission",
    )
    _add_automatic_arguments(once)

    loop = subparsers.add_parser("loop", help="Repeat decision cycles on an interval")
    loop.add_argument(
        "--mode",
        choices=["dry_run", "paper", "live"],
        help="Temporarily override config mode",
    )
    loop.add_argument(
        "--interval-minutes",
        type=_positive_float,
        default=60,
        help="Loop interval",
    )
    loop.add_argument(
        "--max-runs",
        type=_positive_int,
        help="Maximum loop count for testing",
    )
    loop.add_argument(
        "--confirm-live-orders",
        action="store_true",
        help="Final explicit confirmation required before legacy live order submission",
    )
    _add_automatic_arguments(loop)
    buying_power = subparsers.add_parser(
        "buying-power",
        help="Check KIS overseas buying power without submitting an order",
    )
    buying_power.add_argument(
        "--symbol",
        help="Symbol to check; defaults to the first configured symbol",
    )
    buying_power.add_argument("--qty", type=float, default=1.0, help="Share quantity")

    day_test = subparsers.add_parser(
        "day-test",
        help="Plan a one-share same-day KIS buy/sell test",
    )
    day_test.add_argument(
        "--candidate",
        action="append",
        help="Candidate symbol; may be repeated. Defaults to a conservative list.",
    )
    day_test.add_argument("--max-total-usd", type=float, default=64.0)
    day_test.add_argument("--take-profit-pct", type=float, default=1.5)
    day_test.add_argument("--stop-loss-pct", type=float, default=-1.0)
    day_test.add_argument("--max-hold-minutes", type=int, default=180)
    day_test.add_argument(
        "--confirmation-price-tolerance-pct",
        type=float,
        default=1.0,
        help="Allow a stale confirmation limit price within this percent; capped at 2",
    )
    day_test.add_argument(
        "--live-trading",
        action="store_true",
        help="Enable guarded live buy submission after exact final confirmation",
    )
    day_test.add_argument(
        "--dry-run",
        action="store_true",
        help="Force no-order dry-run planning even when config mode is live",
    )
    day_test.add_argument(
        "--record-path",
        default=str(application_data_root() / "logs" / "day_trade_test_orders.jsonl"),
        help="JSONL record path for planned orders and guarded live attempts",
    )

    sell_monitor = subparsers.add_parser(
        "sell-monitor",
        help="Monitor and sell the existing HIVE 1-share position only",
    )
    sell_monitor.add_argument("--take-profit-pct", type=float, default=1.5)
    sell_monitor.add_argument(
        "--stop-loss-enabled",
        action="store_true",
        help="Enable stop-loss checks; disabled by default for profit-or-hold mode",
    )
    sell_monitor.add_argument("--stop-loss-pct", type=float, default=-1.0)
    sell_monitor.add_argument(
        "--trailing-stop-enabled",
        action="store_true",
        help="Enable trailing-stop checks; disabled by default for profit-or-hold mode",
    )
    sell_monitor.add_argument("--trailing-stop-pct", type=float, default=0.8)
    sell_monitor.add_argument(
        "--force-sell-before-close-enabled",
        action="store_true",
        help="Enable force-sell-before-close; disabled by default",
    )
    sell_monitor.add_argument(
        "--force-sell-before-close-minutes",
        type=int,
        default=10,
    )
    sell_monitor.add_argument("--max-retries", type=int, default=3)
    sell_monitor.add_argument("--poll-seconds", type=float, default=30.0)
    sell_monitor.add_argument("--fill-check-seconds", type=float, default=90.0)
    sell_monitor.add_argument("--fill-poll-seconds", type=float, default=10.0)
    sell_monitor.add_argument(
        "--record-path",
        default="logs/hive_sell_monitor.jsonl",
        help="JSONL record path for sell monitor decisions and order results",
    )
    sell_monitor.add_argument(
        "--dry-run",
        action="store_true",
        help="Print and log sell decisions without submitting a sell order",
    )
    sell_monitor.add_argument(
        "--max-loops",
        type=int,
        help="Testing aid: stop after this many monitor loops",
    )

    subparsers.add_parser(
        "live-canary-preflight",
        help="Run trading-API GET-only checks; OAuth token POST may occur",
    )
    canary_arm = subparsers.add_parser(
        "live-canary-arm",
        help="Issue a one-market-date authorization for the bounded live canary",
    )
    canary_arm.add_argument("--market-date", required=True)
    canary_arm.add_argument(
        "--confirm",
        choices=["I UNDERSTAND THIS WILL PLACE REAL ORDERS TODAY"],
        required=True,
    )
    canary = subparsers.add_parser(
        "live-canary",
        help="Run the unattended bounded KIS live canary role",
    )
    canary.add_argument("--max-loops", type=_positive_int, help="Testing aid; production leaves this unset")

    trading_agents = subparsers.add_parser(
        "trading-agents",
        help="Run optional TradingAgents analysis without submitting orders",
    )
    trading_agents.add_argument(
        "--symbol",
        help="Symbol to analyze; defaults to the first configured symbol",
    )
    trading_agents.add_argument(
        "--date",
        dest="analysis_date",
        help="Analysis date in YYYY-MM-DD; defaults to today",
    )
    trading_agents.add_argument("--asset-type", default="stock")
    trading_agents.add_argument(
        "--analyst",
        action="append",
        help="TradingAgents analyst to include; may be repeated",
    )
    trading_agents.add_argument("--llm-provider")
    trading_agents.add_argument("--deep-think-llm")
    trading_agents.add_argument("--quick-think-llm")
    trading_agents.add_argument("--backend-url")
    trading_agents.add_argument("--output-language")
    trading_agents.add_argument("--max-debate-rounds", type=int)
    trading_agents.add_argument("--max-risk-discuss-rounds", type=int)
    trading_agents.add_argument("--debug", action="store_true")

    return parser


def _add_automatic_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--auto-select",
        action="store_true",
        help="Select symbols from the promoted learned strategy",
    )
    command.add_argument(
        "--trading-config",
        default="trading_config.json",
        help="Path to automatic trading settings JSON",
    )
