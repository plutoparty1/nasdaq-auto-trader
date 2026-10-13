"""Explicit preflight, approval and start lifecycle; opening never grants authority."""
from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import replace
from datetime import UTC, datetime

from .ai_quant_lab.audit_logger import AuditLogger
from .ai_quant_lab.types import JsonObject
from .automatic_order_guard import AutomaticOrderGuard
from .config_settings import SettingsError
from .live_authorization import broker_authorization_digest
from .live_authorization_store import LiveAuthorizationStore
from .live_canary_lease import BrokerLeaseError, BrokerLiveLease
from .live_session_authorization import SessionAuthorizationRequest
from .market_hours import regular_market_session
from .models import AccountSnapshot, OrderRequest, OrderSide
from .production_authorization import (
    ProductionApprovalRequest,
    ProductionBinding,
    ProductionOrderGate,
    authorize_production_session,
)
from .production_baseline import ProductionBaselineStore
from .production_checks import (
    artifacts,
    conflicting_processes,
    make_client,
    owned_sell_block,
    preflight,
)
from .production_engine import ProductionController, ProductionEngineFactory
from .production_fees import FeeScheduleInput, load_fee_schedule
from .production_ownership import ProductionSessionStore
from .production_policy import configure_production_gate
from .production_runtime import BUILD_ID, STRATEGY_ID, ProductionRuntime, load_runtime
from .production_sizing import candidate_runtime
from .session_state_persistence import load_session_state, save_session_state
from .trading_session_store import TradingSessionStore


class ProductionService:
    def __init__(self, runtime: ProductionRuntime) -> None:
        runtime = candidate_runtime(runtime, load_fee_schedule(runtime))
        self.runtime = runtime
        self.store = LiveAuthorizationStore(runtime.authorization_path)
        self.gate = ProductionOrderGate(runtime.executable, runtime.receipt_path, self.store,
                                        artifacts=artifacts(runtime), current_binding=self._current_binding,
                                        order_checker=self._ownership_block)
        configure_production_gate(self.gate)
        self.factory = ProductionEngineFactory(runtime, self.gate)
        self.controller = ProductionController(
            replace(runtime.config, mode="dry_run", allow_live_trading=False),
            engine_factory=self.factory,
            trading_settings=replace(runtime.settings, dry_run=True, live_trading=False),
            settings_path=runtime.app_dir / "trading_config.json",
            session_store=TradingSessionStore(runtime.session_path),
            interval_seconds=runtime.settings.unattended_interval_minutes * 60,
        )
        self.controller.state = "paused"
        self._review: JsonObject = {}
        self._leases = ExitStack()

    def _current_binding(self) -> ProductionBinding:
        current = load_runtime(self.runtime.app_dir, self.runtime.original_data, self.runtime.executable)
        current = candidate_runtime(current, load_fee_schedule(current))
        return ProductionBinding.capture(current.executable, current.config, current.settings,
                                         artifacts=artifacts(current))

    def _ownership_block(self, order: OrderRequest) -> str:
        return owned_sell_block(self.runtime, order)

    def status(self) -> JsonObject:
        reason = self.gate.reason(self.runtime.config, self.runtime.settings, datetime.now(UTC))
        if reason and self.factory.mode == "live" and self.controller.state == "running":
            self.gate.set_entries_enabled(False)
        return {"build_id": BUILD_ID, "status": self.controller.state,
                "mode": self.factory.mode, "approval_status": reason or "approved_current_session",
                "strategy_id": STRATEGY_ID, "entries_enabled": self.gate.entries_enabled,
                "submission_enabled": self.gate.submission_enabled,
                "real_fill_validation": "not_performed",
                "authorization_warning": "all_orders_blocked;readonly_monitoring_continues:" + reason if reason and self.factory.mode == "live" else ""}

    def preflight(self) -> JsonObject:
        self.runtime = load_runtime(self.runtime.app_dir, self.runtime.original_data, self.runtime.executable)
        base = self.runtime
        self.runtime = candidate_runtime(base, load_fee_schedule(base))
        self.factory.runtime = self.runtime
        result = preflight(self.runtime)
        self._review = result
        path = self.runtime.state_root / "runtime" / "preflight-review.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def review(self) -> JsonObject:
        return self._review or {"status": "blocked", "blockers": ["preflight_required"],
                               "approval_issued": False}

    def prepare_start(self) -> JsonObject:
        from .production_start_flow import prepare_start
        return prepare_start(self)

    def confirm_start(self, confirmation: str, review_digest: str) -> JsonObject:
        result = self.authorize(confirmation, review_digest)
        if result.get("status") != "authorized":
            return result
        return self.start_live(review_digest=review_digest)

    def configure_fees(self, confirmed: bool) -> JsonObject:
        del confirmed
        return {"status": "blocked", "blockers": ["actual_numeric_account_fee_schedule_required"]}

    def configure_fee_profile(self, profile: FeeScheduleInput) -> JsonObject:
        from .production_start_flow import configure_fee_profile
        result = configure_fee_profile(self, profile)
        if result.get("status") == "draft_changed":
            self._review = {}
            self.gate.set_submission_enabled(False)
        return result

    def authorize(self, confirmation: str, review_digest: str) -> JsonObject:
        if self.controller.state == "running":
            return {"status": "blocked", "blockers": ["stop_operation_before_approval"]}
        if not self._review or self._review.get("review_digest") != review_digest:
            return {"status": "blocked", "blockers": ["preflight_review_required"]}
        checked = self.preflight()
        if checked.get("review_digest") != review_digest:
            return {"status": "blocked", "blockers": ["preflight_review_changed"], "review": checked}
        if checked.get("status") != "ready_for_explicit_approval":
            return {"status": "blocked", "blockers": checked.get("blockers", []), "review": checked}
        result = authorize_production_session(ProductionApprovalRequest(
            SessionAuthorizationRequest(self.runtime.config, self.runtime.paths, self.store,
                                        AuditLogger(self.runtime.paths.audit_log_path),
                                        datetime.now(UTC), 12, confirmation),
            self.runtime.executable, self.runtime.receipt_path, self.runtime.settings,
            artifacts(self.runtime),
        ))
        self.gate.set_submission_enabled(False)
        return result

    def _configure_controller(self, mode: str) -> None:
        live = mode == "live"
        self.factory.mode = mode
        self.controller.base_config = replace(self.runtime.config, mode="live" if live else "dry_run",
                                              allow_live_trading=live)
        self.controller.update_settings(replace(self.runtime.settings, dry_run=not live,
                                                live_trading=live))
        path = self.runtime.session_path if live else self.runtime.session_path.with_name("simulation_session.json")
        self.controller.session_store = ProductionSessionStore(
            path, broker_authorization_digest(self.runtime.config),
        ) if live else TradingSessionStore(path)
        self.controller.session_state = load_session_state(self.controller.session_store)
        self.controller.automatic_order_guard = AutomaticOrderGuard(
            self.runtime.paths, self.controller.session_store,
            AuditLogger(self.runtime.paths.audit_log_path),
            authorization_store=self.store if live else LiveAuthorizationStore(
                path.with_suffix(".live-authorization.json")),
            broker_authorization_digest=broker_authorization_digest(self.controller.config),
        )

    def start_live(self, *, review_digest: str = "") -> JsonObject:
        if self.controller.state == "running":
            reason = self.gate.reason(self.runtime.config, self.runtime.settings, datetime.now(UTC))
            if self.factory.mode == "live" and self.gate.submission_enabled and not reason:
                self.gate.set_entries_enabled(True)
                return {**self.status(), "status": "running", "entries_resumed": True}
            return {"status": "blocked", "reason": "stop_operation_before_mode_change"}
        now = datetime.now(UTC)
        reason = self.gate.reason(self.runtime.config, self.runtime.settings, now)
        if reason:
            return {"status": "blocked", "reason": reason}
        checked = self.preflight()
        if review_digest and checked.get("review_digest") != review_digest:
            return {"status": "blocked", "blockers": ["preflight_review_changed"], "review": checked}
        if checked.get("status") != "ready_for_explicit_approval":
            return {"status": "blocked", "blockers": checked.get("blockers", []), "review": checked}
        reason = self.gate.reason(self.runtime.config, self.runtime.settings, now)
        if reason:
            return {"status": "blocked", "reason": reason}
        if not regular_market_session(now).is_open or conflicting_processes(self.runtime):
            return {"status": "blocked", "reason": "production_start_state_changed"}
        pending_leases = ExitStack()
        started = False
        try:
            client = make_client(self.runtime, read_only=False)
            allowed_sides: frozenset[OrderSide] = frozenset({"buy", "sell"})
            lease = pending_leases.enter_context(BrokerLiveLease.acquire(
                self.runtime.original_data / "live_canary" / "broker-live-owner.lock",
                client.account_fingerprint, allowed_sides,
            ))
            client.bind_live_lease(lease)
            self._configure_controller("live")
            account_payload = checked.get("account")
            if not isinstance(account_payload, dict):
                return {"status": "blocked", "reason": "production_account_review_missing"}
            equity = account_payload.get("equity")
            if not isinstance(equity, int | float) or isinstance(equity, bool):
                return {"status": "blocked", "reason": "production_account_review_missing"}
            baseline = ProductionBaselineStore(
                self.runtime.session_path.with_name("production_daily_baseline.json"),
                broker_authorization_digest(self.runtime.config),
            )
            reason = baseline.restore(self.controller.session_state, AccountSnapshot(
                cash=0.0, equity=float(equity), buying_power=0.0,
            ), now)
            if reason:
                return {"status": "blocked", "reason": reason}
            save_session_state(self.controller.session_store, self.controller.session_state)
            self.factory.client = client
            self.controller.start()
            self.gate.set_entries_enabled(True)
            self.gate.set_submission_enabled(True)
            self._leases.close()
            self._leases = pending_leases.pop_all()
            started = True
        except (BrokerLeaseError, SettingsError, OSError) as exc:
            self.gate.set_submission_enabled(False)
            return {"status": "blocked", "reason": getattr(exc, "reason", "production_start_failed")}
        finally:
            pending_leases.close()
            if not started:
                self.gate.set_submission_enabled(False)
                self.factory.client = None
                self.factory.mode = "waiting"
                self.controller.stop()
        return {**self.status(), "status": "running", "mode": "live", "submitted_order": False}

    def start_simulation(self) -> JsonObject:
        if self.controller.state == "running":
            return {"status": "blocked", "reason": "stop_operation_before_mode_change"}
        self.gate.set_submission_enabled(False)
        self._configure_controller("dry_run")
        self.controller.start()
        return {**self.status(), "mode": "dry_run", "submitted_order": False}

    def stop_entries(self) -> JsonObject:
        self.gate.set_entries_enabled(False)
        return {**self.status(), "status": "entries_paused", "protective_monitoring": self.controller.state == "running"}

    def shutdown(self) -> JsonObject:
        self.gate.set_submission_enabled(False)
        self.controller.stop()
        self._leases.close()
        self._leases = ExitStack()
        self.factory.client = None
        self.factory.mode = "waiting"
        return {"status": "stopped", "orders_cancelled": 0, "positions_liquidated": 0,
                "protective_monitoring": False}
