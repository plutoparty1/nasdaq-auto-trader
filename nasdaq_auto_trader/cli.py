"""명령줄에서 자동매매 도구를 실행하는 입구를 제공한다."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .backtest import Backtester
from .config import load_config, validate_trading_mode
from .data import load_bars_csv
from .engine import TradingEngine, decision_to_dict
from .risk import RiskManager
from .strategy import TechnicalStrategy


def build_parser() -> argparse.ArgumentParser:
    """사용자가 실행할 수 있는 명령 목록을 만든다."""

    parser = argparse.ArgumentParser(
        prog="nasdaq-auto-trader",
        description="NASDAQ indicator-driven auto trading helper",
    )
    parser.add_argument("--config", help="JSON 설정 파일 경로")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show-config", help="현재 설정을 JSON으로 보여준다")

    backtest = subparsers.add_parser("backtest", help="CSV 과거 데이터로 백테스트한다")
    backtest.add_argument("--csv", required=True, help="봉 데이터 CSV 경로")
    backtest.add_argument("--cash", type=float, default=10_000, help="시작 현금")

    once = subparsers.add_parser("once", help="현재 시점 기준으로 한 번 판단한다")
    once.add_argument(
        "--mode",
        choices=["dry_run", "paper", "live"],
        help="설정 파일의 실행 모드를 임시로 덮어쓴다",
    )

    loop = subparsers.add_parser("loop", help="정해진 간격으로 자동매매 판단을 반복한다")
    loop.add_argument(
        "--mode",
        choices=["dry_run", "paper", "live"],
        help="설정 파일의 실행 모드를 임시로 덮어쓴다",
    )
    loop.add_argument("--interval-minutes", type=float, default=60, help="반복 간격")
    loop.add_argument("--max-runs", type=int, help="테스트용 최대 반복 횟수")

    return parser


def main(argv: list[str] | None = None) -> int:
    """명령줄 인자를 읽고 알맞은 기능을 실행한다."""

    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if getattr(args, "mode", None):
        config = _replace_mode(config, args.mode)

    if args.command == "show-config":
        print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "backtest":
        result = _run_backtest(config, Path(args.csv), args.cash)
        print(
            json.dumps(
                {
                    "starting_cash": result.starting_cash,
                    "ending_value": round(result.ending_value, 2),
                    "return_pct": round(result.return_pct, 2),
                    "trades": [trade.__dict__ for trade in result.trades],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "once":
        validate_trading_mode(config)
        print(json.dumps(_run_once(config), ensure_ascii=False, indent=2))
        return 0

    if args.command == "loop":
        validate_trading_mode(config)
        _run_loop(config, args.interval_minutes, args.max_runs)
        return 0

    raise ValueError(f"unknown command: {args.command}")


def _run_backtest(config, csv_path: Path, cash: float):
    """설정된 전략과 위험관리로 CSV 백테스트를 실행한다."""

    bars = load_bars_csv(csv_path)
    strategy = TechnicalStrategy(config.strategy)
    risk_manager = RiskManager(config.risk)
    return Backtester(strategy, risk_manager).run(bars, starting_cash=cash)


def _run_once(config):
    """엔진을 한 번 실행하고 JSON으로 찍기 쉬운 결과를 만든다."""

    engine = TradingEngine(config)
    output = []
    for item in engine.run_once():
        output.append(
            {
                "symbol": item["symbol"],
                "decision": decision_to_dict(item["decision"]),
                "order": item["order"].to_alpaca_payload()
                if item["order"] is not None
                else None,
                "response": item["response"],
            }
        )
    return output


def _run_loop(config, interval_minutes: float, max_runs: int | None) -> None:
    """정해진 시간마다 한 번 실행을 반복한다."""

    if interval_minutes <= 0:
        raise ValueError("interval-minutes must be greater than zero")

    run_count = 0
    while True:
        run_count += 1
        print(json.dumps(_run_once(config), ensure_ascii=False))
        if max_runs is not None and run_count >= max_runs:
            return
        time.sleep(interval_minutes * 60)


def _replace_mode(config, mode: str):
    """frozen dataclass의 실행 모드만 새 값으로 바꾼다."""

    from dataclasses import replace

    return replace(config, mode=mode)
