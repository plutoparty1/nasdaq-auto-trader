from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from .ai_quant_lab.artifact_paths import StrategyArtifactPaths
from .ai_quant_lab.audit_logger import NullAuditLogger
from .automatic_order_guard import AutomaticOrderGuard
from .config import AppConfig
from .config_settings import TradingSettings
from .daily_buy_objective import daily_minimum_decision
from .engine import TradingEngine
from .models import AccountSnapshot, Bar, OrderRequest, Position, TradeDecision
from .operational_signal_gate import gate_decision
from .risk import RiskConfig, RiskManager
from .safe_runtime import BUILD_ID
from .strategy import TechnicalStrategy
from .trading_session_store import TradingSessionStore


class ForbiddenBroker:
    def submit_order(self, order: OrderRequest) -> dict[str, str]:
        raise AssertionError("offline_replay_broker_submission_forbidden")


def _synthetic_bars() -> list[Bar]:
    now = datetime(2026, 10, 9, 20, tzinfo=UTC)
    dates: list[datetime] = []
    while len(dates) < 100:
        if now.weekday() < 5:
            dates.append(now)
        now -= timedelta(days=1)
    result = []
    for index, timestamp in enumerate(reversed(dates)):
        price = 20.61 + (99 - index) * 0.04
        result.append(Bar("CMCSA", timestamp.strftime("%Y%m%d"), price,
                          price + 0.02, price - 0.02, price, 1000))
    return result


def _engine(config: AppConfig, directory: Path, now: datetime, settings: TradingSettings) -> TradingEngine:
    paths = StrategyArtifactPaths.from_root(directory / "artifacts")
    store = TradingSessionStore(directory / "session.json")
    guard = AutomaticOrderGuard(paths, store, NullAuditLogger())
    return TradingEngine(
        config, broker=ForbiddenBroker(), account=AccountSnapshot(62.91, 62.91, 62.91),
        positions={}, trading_settings=replace(settings, auto_symbol_selection_enabled=False),
        strategy_artifact_paths=paths, automatic_order_guard=guard, clock=lambda: now,
    )


def run_replay(output: Path, root: Path) -> None:
    from .safe_launcher import load_effective_runtime

    effective = load_effective_runtime(root)
    config = effective.config
    now = datetime(2026, 10, 12, 13, 40, tzinfo=UTC)
    bars = _synthetic_bars()
    strategy = TechnicalStrategy(config.strategy)
    raw = strategy.decide("CMCSA", bars, None)
    corrected = daily_minimum_decision(strategy, raw, bars, None, due=True)
    held = Position("CMCSA", 1, 20.61, 20.61)
    raw_sell = strategy.decide("CMCSA", bars, held)
    if raw.score != 0 or corrected.action != "hold" or raw_sell.action != "sell":
        raise AssertionError("captured_signal_mechanism_not_reproduced")
    cases = []
    with TemporaryDirectory(prefix="roundtrip-offline-") as temporary:
        work = Path(temporary)
        engine = _engine(config, work, now, effective.settings)
        for index in range(3):
            [item] = engine._run_rule_decision_cycle(
                {"CMCSA": bars}, AccountSnapshot(62.91, 62.91, 62.91), {},
                symbols=["CMCSA"], entry_symbols={"CMCSA"}, daily_minimum_symbol="CMCSA",
            )
            if item["decision"].action != "hold" or item["order"] is not None:
                raise AssertionError("no_signal_generated_order")
            cases.append({"case": f"no_signal_cycle_{index}",
                          "decision": asdict(item["decision"]), "order": None})
        rising = [Bar(bar.symbol, bar.timestamp, 16.65 + index * 0.04,
                      16.67 + index * 0.04, 16.63 + index * 0.04,
                      16.65 + index * 0.04, bar.volume)
                  for index, bar in enumerate(bars)]
        funded = AccountSnapshot(1000, 1000, 1000)
        entry_engine = _engine(config, work / "normal-entry", now, effective.settings)
        [entry] = entry_engine._run_rule_decision_cycle(
            {"CMCSA": rising}, funded, {}, symbols=["CMCSA"], entry_symbols={"CMCSA"},
        )
        if (entry["decision"].action != "buy" or entry["order"] is None
                or entry["order"].qty != 1
                or entry["response"]["reason"] != "safe_release_order_lock"
                or entry["response"]["submitted_order"] is not False):
            raise AssertionError("normal_entry_plan_or_transmission_lock_failed")
        cases.append({"case": "normal_entry_order_plan", "input_scope": "offline_synthetic_only",
                      "account": asdict(funded), "decision": asdict(entry["decision"]),
                      "order": asdict(entry["order"]), "response": entry["response"],
                      "risk_costs": entry["risk_costs"]})
        restarted = _engine(config, work, now + timedelta(minutes=5), effective.settings)
        [opposite] = restarted._run_rule_decision_cycle(
            {"CMCSA": bars}, AccountSnapshot(62.91, 62.91, 62.91), {"CMCSA": held},
            symbols=["CMCSA"], entry_symbols=set(),
        )
        if opposite["decision"].action != "hold":
            raise AssertionError("same_completed_bar_opposite_after_restart")
        cases.append({"case": "same_bar_opposite_after_restart",
                      "decision": asdict(opposite["decision"])})
        next_day = _engine(config, work, now + timedelta(days=1), effective.settings)
        next_bars = [*bars, Bar("CMCSA", "20261012", 20.60, 20.62, 20.58, 20.60, 1000)]
        [new_risk] = next_day._run_rule_decision_cycle(
            {"CMCSA": next_bars}, AccountSnapshot(62.91, 62.91, 62.91), {"CMCSA": held},
            symbols=["CMCSA"], entry_symbols=set(),
        )
        if new_risk["decision"].action != "sell":
            raise AssertionError("new_completed_bar_technical_risk_sell_blocked")
        cases.append({"case": "new_completed_bar_technical_risk_sell",
                      "decision": asdict(new_risk["decision"]), "response": new_risk["response"]})
        losing = replace(held, market_value=19)
        [protective] = restarted._run_rule_decision_cycle(
            {"CMCSA": bars}, AccountSnapshot(62.91, 62.91, 62.91), {"CMCSA": losing},
            symbols=["CMCSA"], entry_symbols=set(),
        )
        if (protective["decision"].action != "sell"
                or protective["response"]["reason"] != "safe_release_order_lock"):
            raise AssertionError("protective_exit_not_preserved_or_order_lock_missing")
        cases.append({"case": "new_mark_protective_sell_at_loss",
                      "decision": asdict(protective["decision"]),
                      "response": protective["response"], "risk_costs": protective["risk_costs"]})
        winning = replace(held, market_value=22)
        [profit] = restarted._run_rule_decision_cycle(
            {"CMCSA": bars}, AccountSnapshot(62.91, 62.91, 62.91), {"CMCSA": winning},
            symbols=["CMCSA"], entry_symbols=set(),
        )
        if profit["decision"].action != "sell":
            raise AssertionError("take_profit_path_missing")
        cases.append({"case": "take_profit_cost_diagnostics",
                      "decision": asdict(profit["decision"]), "risk_costs": profit["risk_costs"]})
        gate_store = TradingSessionStore(work / "contract.json")
        for action in ("buy", "sell", "buy"):
            result = gate_decision(gate_store, "contract", "v1", "CMCSA", bars,
                                   TradeDecision("CMCSA", action, 8, 20.61, ["synthetic_contract"]), now)
            cases.append({"case": f"general_contract_{action}", "decision": asdict(result)})
        if result.action != "hold":
            raise AssertionError("same_bar_reentry_not_blocked")
    account = AccountSnapshot(54.0728143546, 54.0728143546, 54.0728143546)
    risk = RiskManager(RiskConfig(max_position_pct=1, order_qty=1, risk_per_trade_pct=0.02))
    mandatory = TradeDecision("CMCSA", "buy", 8, 20.61, ["synthetic_valid_entry"], 1.6488)
    if risk.build_order(mandatory, account, None, 20.61) is not None:
        raise AssertionError("mandatory_one_share_risk_regression")
    cross_process = gate_decision(
        TradingSessionStore(root / "simulation" / "frozen-restart-v3.json"),
        "offline_restart", "frozen-restart-v2", "CMCSA", bars, mandatory, now,
    )
    if any(reason.startswith("session_store_") for reason in cross_process.reasons):
        raise AssertionError("cross_process_persistence_failed")
    payload = {
        "build_id": BUILD_ID, "mode": "dry_run", "order_lock": True,
        "historical_data_scope": "captured_decision_and_fill_fields;synthetic_OHLCV_not_historical_replay",
        "effective_strategy_config": asdict(config.strategy),
        "effective_risk_config": asdict(config.risk),
        "effective_order_qty": effective.settings.order_qty,
        "historical_original_observed": {"buy_score": 0, "buy_action": "buy",
                                         "sell_score": 9, "sell_action": "sell"},
        "synthetic_raw_buy": asdict(raw), "synthetic_raw_sell": asdict(raw_sell),
        "corrected_minimum_decision": asdict(corrected), "cases": cases,
        "mandatory_risk_case": {"equity": account.equity, "price": 20.61,
                                "stop_pct": 0.08, "planned_loss_excluding_cost": 1.6488,
                                "budget": account.equity * 0.02, "order": None},
        "cross_process_decision": asdict(cross_process),
        "broker_submission_count": 0, "cancel_count": 0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("FROZEN_REPLAY " + json.dumps({"build_id": BUILD_ID, "mode": "dry_run",
          "order_lock": True, "broker_submission_count": 0, "no_signal_buys": 0,
          "protective_sell": "preserved", "mandatory_risk_order": None,
          "restart_action": cross_process.action}), flush=True)
