from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import assert_never

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditLogger
from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestEngine
from nasdaq_auto_trader.ai_quant_lab.config import (
    AIQuantConfig,
    live_order_block_reason,
    load_ai_quant_config,
    validate_ai_quant_config,
)
from nasdaq_auto_trader.ai_quant_lab.insane_search_research import (
    CommandInsaneSearchRunner,
    DisabledInsaneSearchRunner,
    InsaneSearchResearchService,
    ResearchContext,
)
from nasdaq_auto_trader.ai_quant_lab.operator_models import (
    OperatorPaths,
    TradeSide,
    UnsupportedCommandError,
)
from nasdaq_auto_trader.ai_quant_lab.operator_market_data import load_bars_json
from nasdaq_auto_trader.ai_quant_lab.paper_shadow import (
    PaperShadowEngine,
    PaperShadowLedger,
    PaperShadowMode,
    PaperShadowRequest,
)
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.scoring_engine import ScoringEngine
from nasdaq_auto_trader.ai_quant_lab.self_improvement_loop import SelfImprovementLoop
from nasdaq_auto_trader.ai_quant_lab.strategy_factory import AIStrategyFactory
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine
from nasdaq_auto_trader.config import load_config
from nasdaq_auto_trader.execution.live_integration import (
    AIQuantRuntimePaths,
    run_ai_quant_live_cycle,
)
from nasdaq_auto_trader.execution.position_sizer import PortfolioState
from nasdaq_auto_trader.strategies.base_strategy import TargetPosition


@dataclass(frozen=True, slots=True)
class FileStrategySpecProvider:
    candidate_path: Path | None

    def request_strategy_specs(
        self,
        prompt: str,
        context: ResearchContext,
    ) -> tuple[str, ...]:
        del prompt, context
        if self.candidate_path is None:
            return ()
        try:
            return (self.candidate_path.read_text(encoding="utf-8"),)
        except OSError:
            return ()


def status_payload(paths: OperatorPaths) -> JsonObject:
    config = load_ai_quant_config(paths.ai_config_path)
    validation = validate_ai_quant_config(config)
    registry = strategy_registry(paths, config)
    promoted = registry.load_promoted_strategy()
    return {
        "command": "status",
        "config_valid": validation.valid,
        "config_reasons": list(validation.reasons),
        "live_block_reason": live_order_block_reason(config) or "",
        "registry_records": len(registry.load_records()),
        "promoted_present": promoted is not None,
        "promoted_status": promoted_status(promoted),
    }


def nightly_payload(args: argparse.Namespace, paths: OperatorPaths) -> JsonObject:
    config = load_ai_quant_config(paths.ai_config_path)
    audit = AuditLogger(paths.audit_log_path)
    loop = SelfImprovementLoop(
        config,
        InsaneSearchResearchService(config, research_runner(args, config), audit, paths.spec_dir / "research"),
        AIStrategyFactory(FileStrategySpecProvider(optional_path(args.candidate_json)), audit, paths.spec_dir),
        BacktestEngine(config, audit),
        ValidationEngine(audit),
        ScoringEngine(audit),
        strategy_registry(paths, config),
        audit,
    )
    result = loop.run_once(load_bars_json(optional_path(args.bars_json)))
    return {
        "command": "nightly",
        "status": result.status,
        "experiment_id": result.experiment_id,
        "generated_candidates": result.generated_candidates,
        "accepted_candidates": result.accepted_candidates,
        "reasons": list(result.reasons),
    }


def champion_lock_payload(args: argparse.Namespace, paths: OperatorPaths) -> JsonObject:
    config = load_ai_quant_config(paths.ai_config_path)
    registry = strategy_registry(paths, config)
    record = next(
        (
            item
            for item in registry.load_records()
            if item.strategy_id == args.strategy_id and item.version == args.strategy_version
        ),
        None,
    )
    if record is None:
        return {"command": "champion-lock", "status": "blocked", "reasons": ["strategy_record_missing"]}
    decision = registry.lock_champion(record, risk_snapshot(config))
    return {
        "command": "champion-lock",
        "status": "completed" if decision.allowed else "blocked",
        "reasons": list(decision.reasons),
        "target_status": decision.target_status.value,
    }


def rollback_payload(args: argparse.Namespace, paths: OperatorPaths) -> JsonObject:
    config = load_ai_quant_config(paths.ai_config_path)
    decision = strategy_registry(paths, config).rollback_to_no_trade(args.reason)
    return {
        "command": "rollback",
        "status": "completed" if decision.allowed else "blocked",
        "reasons": list(decision.reasons),
        "target_status": decision.target_status.value,
    }


def paper_shadow_payload(args: argparse.Namespace, paths: OperatorPaths) -> JsonObject:
    config = load_ai_quant_config(paths.ai_config_path)
    audit = AuditLogger(paths.audit_log_path)
    result = PaperShadowEngine(config, audit).run(paper_shadow_request(args))
    if args.ledger_path:
        PaperShadowLedger(Path(args.ledger_path), audit).append(result)
    return {
        "command": "paper-shadow",
        "status": result.status,
        "fills": len(result.fills),
        "submitted_orders": result.submitted_orders,
        "blocked_reasons": list(result.blocked_reasons),
    }


def live_cycle_payload(args: argparse.Namespace, paths: OperatorPaths) -> JsonObject:
    result = run_ai_quant_live_cycle(load_config(args.app_config), runtime_paths(paths))
    return {
        "command": "live-cycle",
        "status": result.status,
        "submitted_orders": result.submitted_orders,
        "blocked_reasons": list(result.blocked_reasons),
    }


def paper_shadow_request(args: argparse.Namespace) -> PaperShadowRequest:
    side = trade_side(args.side)
    symbol = args.symbol.upper()
    return PaperShadowRequest(
        args.strategy_id,
        args.strategy_version,
        paper_mode(args.mode),
        (TargetPosition(symbol, side, 1.0, 1.0, args.price, stop_price(args.price, side), args.strategy_id),),
        PortfolioState(args.equity, args.cash, {}, 0.0),
        {symbol: args.price},
        datetime.now(timezone.utc).isoformat(),
    )


def strategy_registry(paths: OperatorPaths, config: AIQuantConfig) -> StrategyRegistry:
    return StrategyRegistry(paths.registry_path, paths.promoted_path, config, AuditLogger(paths.audit_log_path))


def runtime_paths(paths: OperatorPaths) -> AIQuantRuntimePaths:
    return AIQuantRuntimePaths(paths.ai_config_path, paths.registry_path, paths.promoted_path, paths.spec_dir, paths.audit_log_path)


def research_runner(
    args: argparse.Namespace,
    config: AIQuantConfig,
) -> CommandInsaneSearchRunner | DisabledInsaneSearchRunner:
    command = (
        tuple(args.insane_search_command)
        if args.insane_search_command
        else config.insane_search_command
    )
    if command:
        return CommandInsaneSearchRunner(command, config.insane_search_timeout_seconds)
    return DisabledInsaneSearchRunner()


def paper_mode(value: str) -> PaperShadowMode:
    if value == "paper" or value == "shadow":
        return value
    raise UnsupportedCommandError(value)


def trade_side(value: str) -> TradeSide:
    if value == "buy" or value == "sell":
        return value
    raise UnsupportedCommandError(value)


def optional_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def promoted_status(promoted: JsonObject | None) -> str:
    if promoted is None:
        return ""
    status = promoted.get("status")
    return status.strip() if isinstance(status, str) else ""


def risk_snapshot(config: AIQuantConfig) -> JsonObject:
    return {
        "max_single_position_pct": config.max_single_position_pct,
        "max_total_exposure_pct": config.max_total_exposure_pct,
        "max_daily_loss_pct": config.max_daily_loss_pct,
    }


def stop_price(price: float, side: TradeSide) -> float:
    match side:
        case "buy":
            return price * 0.98
        case "sell":
            return price * 1.02
        case unreachable:
            assert_never(unreachable)
