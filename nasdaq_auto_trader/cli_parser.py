from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the command parser."""

    parser = argparse.ArgumentParser(
        prog="nasdaq-auto-trader",
        description="NASDAQ rule-based auto trading helper",
    )
    parser.add_argument("--config", help="Path to a JSON configuration file")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show-config", help="Print effective configuration as JSON")

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
    backtest.add_argument("--cash", type=float, default=10_000, help="Starting cash")

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
    loop.add_argument("--interval-minutes", type=float, default=60, help="Loop interval")
    loop.add_argument("--max-runs", type=int, help="Maximum loop count for testing")
    loop.add_argument(
        "--confirm-live-orders",
        action="store_true",
        help="Final explicit confirmation required before legacy live order submission",
    )
    _add_automatic_arguments(loop)
    loop.add_argument("--live-auth-minutes", type=int)
    loop.add_argument("--live-max-cycles", type=int)

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
        default="logs/day_trade_test_orders.jsonl",
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
