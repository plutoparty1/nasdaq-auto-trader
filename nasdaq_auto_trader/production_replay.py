from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from .ai_quant_lab.types import JsonObject
from .broker import KISCredentials
from .brokers.kis_reconciliation import KISOrderHistory
from .models import AccountSnapshot
from .production_candidate_replay import run_candidate_cases
from .production_ownership import ProductionSessionStore
from .production_replay_market import ReplayMarket
from .production_replay_support import ReplayRuntime, _approve, _engine, _gate, _summary
from .session_claims import AcceptedBuyReceipt, ClaimStatus, SignalKey


def _blocked_socket(*_args: str, **_kwargs: str) -> None:
    raise AssertionError("isolated_replay_network_forbidden")



def run_replay(output: Path, runtime: ReplayRuntime) -> None:
    from . import production_policy
    now = datetime(2026, 10, 13, 14, 30, tzinfo=UTC)
    credentials = KISCredentials("test-only", "test-only", "00000000", paper=False)
    runtime = replace(runtime, config=replace(runtime.config, mode="live", broker="kis",
                      allow_live_trading=True, live_environment_authorized=True, kis=credentials),
                      settings=replace(runtime.settings, dry_run=False, live_trading=True,
                      auto_symbol_selection_enabled=True, automatic_session_authorization_enabled=False,
                      require_confirm_before_buy=False, require_confirm_before_sell=False))
    candidate = runtime
    runtime = replace(runtime, config=replace(runtime.config, risk=replace(runtime.config.risk,
                      integer_quantity_enabled=False, order_qty=1, max_position_qty=1)),
                      settings=replace(runtime.settings, order_qty=1, max_position_qty=1))
    cases: JsonObject = {}
    with TemporaryDirectory(prefix="nasdaq-production-isolated-") as temporary:
        root = Path(temporary)
        with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "appdata")}), \
             patch.object(production_policy, "_gate", None), \
             patch.object(socket.socket, "connect", _blocked_socket), \
             patch.object(socket.socket, "connect_ex", _blocked_socket), \
             patch.object(socket, "create_connection", _blocked_socket):
            for name in ("approval_none", "approval_expired", "account_mismatch", "config_mismatch",
                         "settings_mismatch", "build_mismatch", "valid", "score_zero", "cash_limit",
                         "single_position_limit", "risk_limit", "ambiguous", "partial_fill",
                         "entries_paused", "protective_sell", "all_orders_paused", "foreign_position"):
                directory = root / name
                market = ReplayMarket(directory, credentials)
                if name == "score_zero":
                    market.rising = False
                if name == "cash_limit":
                    market.account = AccountSnapshot(10, 1000, 10)
                if name == "single_position_limit":
                    market.account = AccountSnapshot(62.91, 62.91, 62.91)
                current = runtime
                if name == "score_zero":
                    current = replace(runtime, settings=replace(runtime.settings, daily_minimum_buy_enabled=True))
                if name == "risk_limit":
                    current = replace(runtime, config=replace(runtime.config,
                        risk=replace(runtime.config.risk, risk_per_trade_pct=.00001)))
                engine = _engine(current, directory, market, now)
                test_executable = directory / "test-build.exe"
                test_executable.write_bytes(runtime.executable.read_bytes())
                gate = _gate(engine, test_executable, directory)
                if name != "approval_none":
                    _approve(engine, test_executable, directory, now)
                if name == "approval_expired":
                    engine._clock = lambda: now + timedelta(days=1)
                if name == "account_mismatch":
                    engine.config = replace(current.config, kis=replace(credentials, account_no="00000001"))
                if name == "config_mismatch":
                    engine.config = replace(current.config, risk=replace(current.config.risk, min_cash_buffer_pct=.10))
                if name == "settings_mismatch":
                    engine.trading_settings = replace(current.settings, unattended_interval_minutes=6)
                if name == "build_mismatch":
                    with test_executable.open("ab") as changed:
                        changed.write(b"test-only-build-change")
                if name == "ambiguous":
                    market.response = {"status": "unknown"}
                if name == "partial_fill":
                    market.response = {"status": "partially_filled", "id": "test-only-1"}
                if name in {"entries_paused", "protective_sell"}:
                    gate.set_entries_enabled(False)
                if name in {"protective_sell", "all_orders_paused", "foreign_position"}:
                    from .models import Position
                    market.positions = {"CMCSA": Position("CMCSA", 1, 19, 20.61)}
                if name == "protective_sell":
                    receipt = AcceptedBuyReceipt("owned-test-buy", "CMCSA", "2026-10-13", 0)
                    key = SignalKey("2026-10-13", "test", "v1", "CMCSA", "buy", "owned")
                    store = engine.automatic_order_guard.session_store
                    if not isinstance(store, ProductionSessionStore):
                        raise TypeError("production_session_store_required")
                    store.claim(key)
                    store.complete(key, ClaimStatus.SUBMITTED, receipt)
                    market.history = (KISOrderHistory("owned-test-buy", "CMCSA", "buy", 1, 1,
                                                      20.61, "filled", now),)
                if name == "all_orders_paused":
                    gate.set_submission_enabled(False)
                mismatch_reasons = {
                    "approval_expired": "production_approval_expired",
                    "account_mismatch": "production_account_mismatch",
                    "config_mismatch": "production_config_mismatch",
                    "settings_mismatch": "production_settings_mismatch",
                    "build_mismatch": "production_build_mismatch",
                }
                if name in mismatch_reasons and gate.reason(engine.config, engine.trading_settings,
                                                             engine._clock()) != mismatch_reasons[name]:
                    raise AssertionError(f"approval_mismatch_not_detected:{name}")
                results = engine.run_once()
                cases[name] = _summary(engine, market, results)
                if name == "score_zero":
                    raw = engine.strategy.decide("CMCSA", market.get_stock_bars(["CMCSA"], "1Day", "")["CMCSA"], None)
                    if raw.score != 0 or raw.action != "hold" or any(item["order"] is not None for item in results):
                        raise AssertionError("minimum_buy_forced_zero_signal")
                    cases["score_zero_strategy_diagnostics"] = asdict(raw)
                if name == "single_position_limit":
                    cases["single_position_cap_calculation"] = {"equity": 62.91,
                        "single_position_pct": .05, "cap_dollars": 62.91 * .05,
                        "one_share_price": 20.61, "allowed": False}
                if name == "valid":
                    if len(market.requests) != 1 or market.last_order_qty != "1":
                        raise AssertionError(f"normal_full_chain_not_once:{cases[name]}")
                    engine.run_once()
                    restarted = _engine(current, directory, market, now + timedelta(minutes=5))
                    _gate(restarted, test_executable, directory)
                    restarted.run_once()
                    if len(market.requests) != 1:
                        raise AssertionError("restart_duplicate_fake_order")
                    cases["valid_restart_request_count"] = len(market.requests)
                elif name in {"ambiguous", "partial_fill"}:
                    if len(market.requests) != 1:
                        raise AssertionError(f"reconciliation_initial_order_missing:{cases[name]}")
                    market.latest_day += timedelta(days=1)
                    from .models import Position
                    if name == "partial_fill":
                        market.pending = ()
                        market.positions = {}
                        market.history = (KISOrderHistory("test-only-1", "CMCSA", "buy", 1, .5,
                                                     20.61, "partially_filled", now),)
                    restarted = _engine(current, directory, market, now + timedelta(days=1))
                    _gate(restarted, test_executable, directory)
                    _approve(restarted, test_executable, directory, now + timedelta(days=1))
                    restart_results = restarted.run_once()
                    cases[f"{name}_restart"] = _summary(restarted, market, restart_results)
                    if len(market.requests) != 1:
                        raise AssertionError("reconciliation_duplicate_fake_order")
                    if name == "partial_fill" and market.history_requests == 0:
                        raise AssertionError(f"partial_fill_full_chain_reconciliation_not_exercised:{cases[name + '_restart']}")
                    cases[f"{name}_restart_account_baseline"] = {
                        "scope": "persisted_production_baseline_recovery",
                        "equity": restarted.trading_session_state.starting_equity,
                    }
                elif name == "protective_sell":
                    if len(market.requests) != 1 or not any(item["decision"].action == "sell" for item in results):
                        raise AssertionError("entries_pause_blocked_protective_sell")
                elif market.requests:
                    raise AssertionError(f"blocked_case_submitted:{name}")
            cases["integer_quantity_candidate"] = run_candidate_cases(root, candidate, now)
    payload: JsonObject = {"scope": "test_only_temporary_accounts_and_approvals",
                           "network": "socket_connections_forbidden", "cases": cases,
                           "actual_order_count": 0, "actual_approval_issued": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
