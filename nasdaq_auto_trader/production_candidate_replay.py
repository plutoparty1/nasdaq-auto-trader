from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

from .ai_quant_lab.types import JsonObject
from .brokers.kis_reconciliation import KISOrderHistory
from .live_authorization import broker_authorization_digest
from .models import AccountSnapshot, Position
from .production_fees import FeeSchedule
from .production_ownership import ProductionSessionStore
from .production_replay_market import ReplayMarket
from .production_replay_support import ReplayRuntime, _approve, _engine, _gate, _summary
from .session_claims import AcceptedBuyReceipt, ClaimStatus, SignalKey


def run_candidate_cases(root: Path, runtime: ReplayRuntime, now: datetime) -> JsonObject:
    from .production_runtime import ProductionRuntime
    from .production_sizing import candidate_runtime

    template = ProductionRuntime(root, root, runtime.executable, runtime.config,
                                 runtime.settings, runtime.paths)
    fees = FeeSchedule(.0025, 0, 0, "synthetic_test_only_fee_schedule", now.isoformat(),
                       broker_authorization_digest(runtime.config))
    selected = candidate_runtime(template, fees)
    current = replace(runtime, config=selected.config, settings=selected.settings)
    cases: JsonObject = {}
    names = ("valid", "approval_none", "approval_expired", "account_mismatch", "config_mismatch",
             "settings_mismatch", "build_mismatch", "small_account", "score_zero", "cash_limit",
             "risk_limit", "partial_fill", "ambiguous", "protective_sell", "foreign_position")
    for name in names:
        directory = root / f"candidate-{name}"
        market = ReplayMarket(directory, current.config.kis)
        market.price, market.price_step = 6, .01
        scenario = current
        if name == "small_account":
            market.account = AccountSnapshot(62.91, 62.91, 62.91)
            market.price, market.price_step = 20.61, .04
        if name == "score_zero":
            market.rising = False
            scenario = replace(current, settings=replace(current.settings, daily_minimum_buy_enabled=True))
        if name == "cash_limit":
            market.account = AccountSnapshot(1, 1000, 1)
        if name == "risk_limit":
            scenario = replace(current, config=replace(current.config,
                risk=replace(current.config.risk, risk_per_trade_pct=.00001)))
        engine = _engine(scenario, directory, market, now)
        test_executable = directory / "test-build.exe"
        _ = test_executable.write_bytes(runtime.executable.read_bytes())
        gate = _gate(engine, test_executable, directory)
        if name != "approval_none":
            _approve(engine, test_executable, directory, now)
        if name == "approval_expired":
            engine._clock = lambda: now + timedelta(days=1)
        if name == "account_mismatch":
            engine.config = replace(scenario.config, kis=replace(scenario.config.kis, account_no="00000001"))
        if name == "config_mismatch":
            engine.config = replace(scenario.config, risk=replace(scenario.config.risk, max_order_notional=34))
        if name == "settings_mismatch":
            engine.trading_settings = replace(scenario.settings, unattended_interval_minutes=6)
        if name == "build_mismatch":
            with test_executable.open("ab") as changed:
                _ = changed.write(b"test-only-build-change")
        if name == "ambiguous":
            market.response = {"status": "unknown"}
        if name == "partial_fill":
            market.response = {"status": "partially_filled", "id": "test-only-1"}
        if name in {"protective_sell", "foreign_position"}:
            market.positions = {"CMCSA": Position("CMCSA", 5, 25, 6)}
            gate.set_entries_enabled(False)
        if name == "protective_sell":
            store = engine.automatic_order_guard.session_store
            if not isinstance(store, ProductionSessionStore):
                raise TypeError("production_session_store_required")
            receipt = AcceptedBuyReceipt("owned-test-multiple", "CMCSA", "2026-10-13", 0, 5)
            key = SignalKey("2026-10-13", "test", "v1", "CMCSA", "buy", "owned")
            _ = store.claim(key)
            store.complete(key, ClaimStatus.SUBMITTED, receipt)
            market.history = (KISOrderHistory("owned-test-multiple", "CMCSA", "buy", 5, 5, 6,
                                              "filled", now),)
        results = engine.run_once()
        cases[name] = _summary(engine, market, results)
        if name in {"valid", "partial_fill", "ambiguous", "protective_sell"}:
            if len(market.requests) != 1 or market.last_order_qty != "5":
                raise AssertionError(f"candidate_multi_share_full_chain_failed:{name}:{cases[name]}")
        elif market.requests:
            raise AssertionError(f"candidate_blocked_case_transmitted:{name}")
        if name == "score_zero":
            raw = engine.strategy.decide("CMCSA", market.get_stock_bars(["CMCSA"], "1Day", "")["CMCSA"], None)
            if raw.score != 0 or raw.action != "hold" or any(item["order"] is not None for item in results):
                raise AssertionError("candidate_minimum_forced_zero_score")
            cases["score_zero_raw"] = asdict(raw)
        if name in {"valid", "partial_fill", "ambiguous"}:
            market.latest_day += timedelta(days=1)
            if name == "partial_fill":
                market.history = (KISOrderHistory("test-only-1", "CMCSA", "buy", 5, 2, 6,
                                                  "partially_filled", now),)
            restarted = _engine(scenario, directory, market, now + timedelta(days=1))
            _gate(restarted, test_executable, directory)
            _approve(restarted, test_executable, directory, now + timedelta(days=1))
            cases[f"{name}_restart"] = _summary(restarted, market, restarted.run_once())
            if len(market.requests) != 1:
                raise AssertionError("candidate_restart_duplicate_order")
            if name == "partial_fill" and market.history_requests == 0:
                raise AssertionError("candidate_partial_history_not_reconciled")
    return {"scope": "isolated_test_only_integer_quantity_candidate",
            "candidate_risk_config": asdict(current.config.risk), "cases": cases,
            "multishare_fixture": {"equity": 1000, "price": 6, "max_order_usd": 35,
                                   "expected_integer_qty": 5},
            "small_account_fixture": {"equity": 62.91, "price": 20.61,
                                      "auto_enlarged": False, "expected_order": None}}
