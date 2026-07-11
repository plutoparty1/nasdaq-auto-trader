from __future__ import annotations

import argparse
import json

from nasdaq_auto_trader.ai_quant_lab.operator_runtime import (
    UnsupportedCommandError,
    command_from_text,
    exit_code,
    operator_paths_from_args,
    run_operator_command,
)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "gui":
        return _run_gui(args)
    try:
        command = command_from_text(args.command)
    except UnsupportedCommandError as error:
        print(json.dumps({"error": str(error)}, sort_keys=True))
        return 2
    payload = run_operator_command(command, args, operator_paths_from_args(args))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return exit_code(command, payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nasdaq-auto-trader ai-quant")
    parser.add_argument("--artifact-root")
    parser.add_argument("--ai-config")
    parser.add_argument("--registry-path")
    parser.add_argument("--promoted-path")
    parser.add_argument("--spec-dir")
    parser.add_argument("--audit-log")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Report AI quant fail-closed status")
    gui = subparsers.add_parser("gui", help="Launch the AI quant desktop operator")
    gui.add_argument("--smoke", action="store_true", help="Check GUI controller wiring without opening Tk")
    nightly = subparsers.add_parser("nightly", help="Run one nightly research loop")
    nightly.add_argument("--insane-search-command", nargs="+")
    nightly.add_argument("--candidate-json")
    nightly.add_argument("--bars-json")
    lock = subparsers.add_parser("champion-lock", help="Attempt champion lock")
    lock.add_argument("--strategy-id", required=True)
    lock.add_argument("--strategy-version", required=True)
    rollback = subparsers.add_parser("rollback", help="Rollback promoted strategy to no-trade")
    rollback.add_argument("--reason", required=True)
    monitor = subparsers.add_parser(
        "monitor-degradation",
        help="Rollback promoted strategy when paper/shadow telemetry degrades",
    )
    monitor.add_argument("--ledger-path", required=True)
    shadow = subparsers.add_parser("paper-shadow", help="Run one virtual signal")
    shadow.add_argument("--mode", choices=["paper", "shadow"], default="paper")
    shadow.add_argument("--ledger-path")
    shadow.add_argument("--strategy-id", required=True)
    shadow.add_argument("--strategy-version", required=True)
    shadow.add_argument("--symbol", required=True)
    shadow.add_argument("--side", choices=["buy", "sell"], required=True)
    shadow.add_argument("--price", type=float, required=True)
    shadow.add_argument("--equity", type=float, default=100_000.0)
    shadow.add_argument("--cash", type=float, default=100_000.0)
    live = subparsers.add_parser("live-cycle", help="Run guarded live cycle")
    live.add_argument("--app-config")
    return parser


def _run_gui(args: argparse.Namespace) -> int:
    paths = operator_paths_from_args(args)
    if args.smoke:
        from nasdaq_auto_trader.ai_quant_lab.operator_gui_controller import AIQuantGuiController

        payload = AIQuantGuiController(paths).desktop_smoke_payload()
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    from nasdaq_auto_trader.ai_quant_lab.operator_gui import launch_operator_gui

    return launch_operator_gui(paths)
