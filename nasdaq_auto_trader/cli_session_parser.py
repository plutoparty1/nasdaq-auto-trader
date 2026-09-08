from __future__ import annotations

import argparse


def add_live_session_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    authorize = subparsers.add_parser(
        "authorize-live-session",
        help="Authorize automatic live orders for one NASDAQ regular session",
    )
    authorize.add_argument(
        "--max-attempts",
        type=int,
        choices=range(1, 13),
        default=12,
    )
    authorize.add_argument(
        "--confirm",
        required=True,
    )
    authorize.add_argument(
        "--trading-config",
        default="trading_config.json",
        help="Path to automatic trading settings JSON",
    )
    subparsers.add_parser(
        "revoke-live-session",
        help="Revoke the stored automatic live-session authorization",
    )
