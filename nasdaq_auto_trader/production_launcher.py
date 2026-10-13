"""Formal GUI entrypoint; no approval or execution on launch."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from nasdaq_auto_trader.production_replay import ReplayRuntime, run_replay
from nasdaq_auto_trader.production_runtime import (
    BUILD_ID,
    isolate_runtime,
    load_runtime,
)
from nasdaq_auto_trader.production_service import ProductionService


class Options(argparse.Namespace):
    runtime_check: bool = False
    replay: Path | None = None
    gui_smoke: Path | None = None
    command: str | None = None
    confirm: str = ""
    review_digest: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="정식 운영본: 기본 시작 대기, 기존 승인을 상속하지 않음")
    parser.add_argument("--runtime-check", action="store_true", help="시작 상태 출력; 네트워크/승인/주문 없음")
    parser.add_argument("--replay", type=Path, help="격리된 시험 계좌·승인·가짜 KIS 전송 전체 경로 시험 JSON")
    parser.add_argument("--gui-smoke", type=Path, help="실제 시작대기 GUI 렌더 검증 후 정상 종료; 네트워크·승인·주문 없음")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("preflight", help="읽기 전용 KIS 사전점검; 승인 발급 없음")
    approval = commands.add_parser("authorize-live-session", help="사용자의 명시 승인; 운영 시작은 별도 GUI 버튼")
    approval.add_argument("--confirm", required=True, help="사전점검에 표시된 정확한 승인 문구")
    approval.add_argument("--review-digest", required=True, help="사전점검에서 확인한 조건 해시")
    draft = commands.add_parser("draft-limits", help="명시적인 초안 한도 변경; 프로그램을 닫은 뒤 사용, 승인 발급 없음")
    for option in ("single-position-pct", "total-exposure-pct", "max-order-usd", "risk-per-trade-pct", "stop-loss-pct", "daily-loss-pct", "roundtrip-cost-pct"):
        draft.add_argument("--" + option, type=float, help="백분율은 5=5%%; 금액은 USD. 변경 후 재점검·재승인 필요")
    args = Options()
    _ = parser.parse_args(namespace=args)
    original = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "NasdaqAutoTrader"
    frozen = getattr(sys, "frozen", False)
    executable = Path(sys.executable if frozen else __file__).resolve()
    app_dir = executable.parent if frozen else Path(__file__).resolve().parents[1] / "deploy-operating/NasdaqAutoTrader"
    runtime = load_runtime(app_dir, original, executable)
    isolate_runtime(runtime)
    if args.replay is not None:
        run_replay(args.replay, ReplayRuntime(runtime.config, runtime.settings, runtime.paths, executable))
        print(json.dumps({"build_id": BUILD_ID, "isolated_replay": str(args.replay), "actual_orders": 0, "actual_approvals": 0}))
        return 0
    if args.command == "draft-limits":
        from nasdaq_auto_trader.production_draft import update_draft
        changes = {name: value for name in ("single_position_pct", "total_exposure_pct", "max_order_usd", "risk_per_trade_pct", "stop_loss_pct", "daily_loss_pct", "roundtrip_cost_pct")
                   if isinstance(value := getattr(args, name), float)}
        print(json.dumps(update_draft(runtime, changes), ensure_ascii=False, indent=2))
        return 0
    service = ProductionService(runtime)
    print("PRODUCTION_RUNTIME " + json.dumps(service.status(), ensure_ascii=False), flush=True)
    if args.gui_smoke is not None:
        from nasdaq_auto_trader.production_gui_smoke import run_gui_smoke
        run_gui_smoke(service, args.gui_smoke)
        return 0
    if args.runtime_check:
        print(json.dumps({"executable": str(executable), "draft": True, "strategy": service.status().get("strategy_id"),
                          "minimum_buy": runtime.settings.daily_minimum_buy_enabled,
                          "quantity_method": "automatic_integer" if service.runtime.config.risk.integer_quantity_enabled else "fixed_quantity",
                          "fixed_qty": service.runtime.config.risk.order_qty,
                          "actual_orders": 0, "actual_approvals": 0}, ensure_ascii=False))
        return 0
    if args.command == "preflight":
        print(json.dumps(service.preflight(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "authorize-live-session":
        review = service.preflight()
        if review.get("review_digest") != args.review_digest:
            print(json.dumps({"status": "blocked", "reason": "preflight_review_changed", "review": review}, ensure_ascii=False))
            return 2
        result = service.authorize(args.confirm, args.review_digest)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "authorized" else 2
    from nasdaq_auto_trader.file_lock import exclusive_file_lock
    from nasdaq_auto_trader.production_gui import launch_production_gui
    with exclusive_file_lock(runtime.state_root / "runtime/gui-instance.lock", 0.05):
        launch_production_gui(service)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
