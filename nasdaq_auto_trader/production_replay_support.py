from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .ai_quant_lab.artifact_paths import StrategyArtifactPaths
from .ai_quant_lab.audit_logger import NullAuditLogger
from .ai_quant_lab.types import JsonObject
from .automatic_order_guard import AutomaticOrderGuard
from .config import AppConfig
from .config_settings import TradingSettings
from .engine import TradingEngine
from .engine_types import EngineCycleItem
from .live_authorization import broker_authorization_digest
from .live_session_authorization import (
    LIVE_SESSION_CONFIRMATION,
    SessionAuthorizationRequest,
)
from .models import OrderRequest
from .production_authorization import ProductionOrderGate
from .production_baseline import ProductionBaselineStore
from .production_ownership import ProductionSessionStore, owned_position
from .production_replay_market import ReplayMarket


@dataclass(frozen=True, slots=True)
class ReplayRuntime:
    config: AppConfig
    settings: TradingSettings
    paths: StrategyArtifactPaths
    executable: Path




def _copy_test_strategy(source: StrategyArtifactPaths, target: StrategyArtifactPaths) -> None:
    target.spec_dir.mkdir(parents=True)
    strategy_id = "builtin_ai_volatility_target"
    version = "data-b230423351524f87-catalogue-v5"
    name = f"{strategy_id}-{version}.json"
    (target.spec_dir / name).write_bytes((source.spec_dir / name).read_bytes())
    target.promoted_path.write_text(json.dumps({
        "active_strategy_id": strategy_id, "strategy_version": version,
        "status": "champion", "allowed_for_live": True, "manual_approval": True,
    }), encoding="utf-8")


def _engine(runtime: ReplayRuntime, directory: Path, market: ReplayMarket,
            now: datetime) -> TradingEngine:
    paths = StrategyArtifactPaths.from_root(directory / "artifacts")
    if not paths.spec_dir.exists():
        _copy_test_strategy(runtime.paths, paths)
    account_digest = broker_authorization_digest(runtime.config)
    guard = AutomaticOrderGuard(paths, ProductionSessionStore(directory / "session.json", account_digest), NullAuditLogger())
    engine = TradingEngine(runtime.config, broker=market, market_data=market,
                         clock=lambda: now, trading_settings=runtime.settings,
                         strategy_artifact_paths=paths, automatic_order_guard=guard,
                         live_order_confirmation=True)
    reason = ProductionBaselineStore(directory / "daily-baseline.json", account_digest).restore(
        engine.trading_session_state, market.get_account(), now)
    if reason:
        raise AssertionError(f"production_baseline_recovery_failed:{reason}")
    return engine


def _approve(engine: TradingEngine, executable: Path, directory: Path, now: datetime) -> None:
    from .production_authorization import (
        ProductionApprovalRequest,
        authorize_production_session,
    )

    result = authorize_production_session(ProductionApprovalRequest(
        SessionAuthorizationRequest(engine.config, engine.strategy_artifact_paths,
                                    engine.automatic_order_guard.authorization_store,
                                    NullAuditLogger(), now, 12, LIVE_SESSION_CONFIRMATION),
        executable, directory / "production-approval.json", engine.trading_settings,
    ))
    if result["status"] != "authorized":
        raise AssertionError(f"test_only_approval_failed:{result}")


def _gate(engine: TradingEngine, executable: Path, directory: Path) -> ProductionOrderGate:
    from .production_policy import configure_production_gate

    gate = ProductionOrderGate(executable, directory / "production-approval.json",
                               engine.automatic_order_guard.authorization_store,
                               order_checker=lambda order: _ownership_block(engine, order))
    gate.set_submission_enabled(True)
    engine.production_order_gate = gate
    configure_production_gate(gate)
    return gate


def _ownership_block(engine: TradingEngine, order: OrderRequest) -> str:
    if order.side != "sell":
        return ""
    market = engine.broker
    if not isinstance(market, ReplayMarket):
        raise TypeError("isolated_replay_broker_required")
    position = market.list_positions(refresh=True).get(order.symbol)
    store = engine.automatic_order_guard.session_store
    if not isinstance(store, ProductionSessionStore):
        raise TypeError("production_session_store_required")
    history = market.list_order_history("20261001", "20261031")
    if position is None or not owned_position(position, store.managed_receipts(), history):
        return "production_position_not_owned"
    return "" if order.qty is not None and order.qty <= position.qty else "production_sell_quantity_changed"


def _summary(engine: TradingEngine, market: ReplayMarket, results: list[EngineCycleItem]) -> JsonObject:
    report = engine.last_selection_report
    return {
        "selection": asdict(report) if report is not None else None,
        "results": [{"decision": asdict(item["decision"]),
                     "order": asdict(item["order"]) if item["order"] is not None else None,
                     "response": item["response"]} for item in results],
        "fake_kis_requests": [request for request in market.requests], "bar_requests": market.bar_requests,
        "open_order_queries": market.open_order_requests, "history_queries": market.history_requests,
        "session_state_saved": engine.automatic_order_guard.session_store.path.is_file(),
        "persisted_safety": asdict(engine.automatic_order_guard.session_store.load_safety_state()),
        "pending_buy_receipt_count": len(engine.automatic_order_guard.session_store.load_buy_receipts()),
    }

