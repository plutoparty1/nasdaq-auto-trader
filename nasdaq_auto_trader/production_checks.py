"""Read-only readiness and public review for the formal production profile."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from .ai_quant_lab.types import JsonObject
from .automatic_risk import AutomaticRiskLimits, resolve_automatic_risk_limits
from .broker import KISCredentials
from .brokers.common import BrokerRequestError
from .brokers.kis_client import KISClient
from .live_canary_preflight import KISPreflightTransportClient
from .live_session_authorization import LIVE_SESSION_CONFIRMATION
from .market_hours import EASTERN, regular_market_session
from .models import OrderRequest
from .production_authorization import ProductionBinding
from .production_fees import load_fee_schedule
from .production_ownership import (
    ProductionSessionStore,
    foreign_portfolio_counts,
    owned_position,
)
from .production_runtime import (
    BUILD_ID,
    SPEC_DIGEST,
    STRATEGY_ID,
    STRATEGY_VERSION,
    ProductionRuntime,
)
from .quant_data.symbol_selector import ResolvedStrategy, resolve_strategy
from .quant_data.universe_snapshot import load_default_universe, universe_freshness
from .trading_session_store import SessionStoreError


class ProductionReadOnlyClient(KISPreflightTransportClient):
    _ALLOWED_TRANSPORT = KISPreflightTransportClient._ALLOWED_TRANSPORT | frozenset({
        ("GET", "/uapi/overseas-stock/v1/trading/inquire-ccnl"),
    })


def artifacts(runtime: ProductionRuntime) -> tuple[Path, ...]:
    return (runtime.app_dir / "config.operating.json", runtime.app_dir / "trading_config.json",
            runtime.app_dir / "fee-review.json", runtime.app_dir / "credential-source.txt",
            runtime.paths.registry_path, runtime.paths.promoted_path,
            runtime.paths.spec_dir / f"{STRATEGY_ID}-{STRATEGY_VERSION}.json",
            runtime.paths.root / "ai_quant_config.json")


def fee_confirmed(runtime: ProductionRuntime) -> bool:
    return load_fee_schedule(runtime) is not None


def make_client(runtime: ProductionRuntime, *, read_only: bool) -> KISClient:
    kis = runtime.config.kis
    credentials = KISCredentials(kis.app_key, kis.app_secret, kis.account_no,
                                 kis.account_product_code, paper=False,
                                 order_exchange_code=kis.order_exchange_code,
                                 price_exchange_code=kis.price_exchange_code,
                                 currency=kis.currency, timeout=kis.timeout)
    client = ProductionReadOnlyClient(credentials) if read_only else KISClient(credentials)
    client._token_cache_path = runtime.token_cache
    client._broker_lease_path = runtime.original_data / "live_canary" / "broker-live-owner.lock"
    return client


def conflicting_processes(runtime: ProductionRuntime) -> list[str]:
    if os.name != "nt":
        return []
    command = ("Get-CimInstance Win32_Process | Where-Object { "
               "$_.Name -like '*NasdaqAutoTrader*' -and $_.ProcessId -ne "
               + str(os.getpid()) + " } | Select-Object ProcessId,Name,ExecutablePath | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                                capture_output=True, text=True, timeout=15, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return ["process_state_unavailable"]
    if result.returncode != 0:
        return ["process_state_unavailable"]
    if not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return ["process_state_unavailable"]
    rows = payload if isinstance(payload, list) else [payload]
    conflicts: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("ProcessId"):
            return ["process_state_unavailable"]
        conflicts.append(str(row.get("ExecutablePath") or (
            "unknown_path:" + str(row.get("Name", "NasdaqAutoTrader")) + ":pid=" + str(row["ProcessId"]))))
    return conflicts


def _readonly_portfolio_counts(runtime: ProductionRuntime) -> tuple[int, int, int, int]:
    held = pending = foreign_held = foreign_pending = 0
    receipts = ProductionSessionStore(runtime.session_path,
        ProductionBinding.capture(runtime.executable, runtime.config, runtime.settings).account_digest
    ).managed_receipts()
    for exchange in ("NASD", "NYSE", "AMEX"):
        scoped = replace(runtime, config=replace(runtime.config, kis=replace(
            runtime.config.kis, order_exchange_code=exchange,
        )))
        reader = make_client(scoped, read_only=True)
        positions, orders = reader.list_positions(refresh=True), reader.list_open_orders()
        held += len(positions)
        pending += len(orders)
        history = reader.list_order_history(
            min(item.market_date for item in receipts).replace("-", ""),
            datetime.now(UTC).astimezone(EASTERN).date().strftime("%Y%m%d"),
        ) if receipts and (positions or orders) else ()
        unknown_positions, unknown_orders = foreign_portfolio_counts(positions, orders, (receipts, history))
        foreign_held += unknown_positions
        foreign_pending += unknown_orders
    return held, pending, foreign_held, foreign_pending


def owned_sell_block(runtime: ProductionRuntime, order: OrderRequest) -> str:
    if order.side != "sell":
        return ""
    try:
        receipts = ProductionSessionStore(runtime.session_path,
            ProductionBinding.capture(runtime.executable, runtime.config, runtime.settings).account_digest
        ).managed_receipts()
        scoped = tuple(item for item in receipts if item.symbol == order.symbol)
        if not scoped:
            return "production_position_not_owned"
        reader = make_client(runtime, read_only=True)
        positions = reader.list_positions(refresh=True)
        position = positions.get(order.symbol)
        if position is None or order.qty is None or not 0 < order.qty <= position.qty:
            return "production_position_not_owned"
        history = reader.list_order_history(
            min(item.market_date for item in scoped).replace("-", ""),
            datetime.now(UTC).astimezone(EASTERN).date().strftime("%Y%m%d"),
        )
        return "" if owned_position(position, scoped, history) else "production_position_not_owned"
    except (SessionStoreError, BrokerRequestError, OSError, ValueError):
        return "production_ownership_reconciliation_unavailable"


def preflight(runtime: ProductionRuntime, now: datetime | None = None) -> JsonObject:
    checked = now or datetime.now(UTC)
    blockers: list[str] = []
    binding = ProductionBinding.capture(runtime.executable, runtime.config, runtime.settings,
                                        artifacts=artifacts(runtime))
    resolved = resolve_strategy("live", runtime.paths)
    if not isinstance(resolved, ResolvedStrategy):
        blockers.append(resolved.reason)
        limits = None
    else:
        if (resolved.spec.strategy_id, resolved.spec.version, resolved.spec_digest) != (
                STRATEGY_ID, STRATEGY_VERSION, SPEC_DIGEST):
            blockers.append("production_strategy_identity_mismatch")
        limits = resolve_automatic_risk_limits(runtime.paths, resolved, candidate_risk=runtime.config.risk)
        if not isinstance(limits, AutomaticRiskLimits):
            blockers.append(limits.reason)
            limits = None
    freshness = universe_freshness(load_default_universe(), "live", checked.date())
    if freshness.blocked_reason:
        blockers.append(freshness.blocked_reason)
    if not regular_market_session(checked).is_open:
        blockers.append("outside_regular_session")
    if not fee_confirmed(runtime):
        blockers.append("actual_fee_review_required")
    conflicts = conflicting_processes(runtime)
    if conflicts:
        blockers.append("other_trader_process_present")
    account: JsonObject = {}
    held, pending = 0, 0
    try:
        client = make_client(runtime, read_only=True)
        snapshot = client.get_account(refresh=True)
        account = asdict(snapshot)
        held, pending, foreign_held, foreign_pending = _readonly_portfolio_counts(runtime)
        if foreign_held:
            blockers.append("existing_positions_require_separate_management_review")
        if foreign_pending:
            blockers.append("existing_open_orders_require_reconciliation")
        if snapshot.cash <= 0 or snapshot.equity <= 0:
            blockers.append("account_funding_required")
    except (BrokerRequestError, OSError, ValueError):
        blockers.append("kis_readonly_account_unavailable")
    except SessionStoreError as exc:
        blockers.append(exc.reason)
    effective: JsonObject = {
        "quantity_method": "cost_inclusive_integer_risk_budget" if runtime.settings.integer_quantity_enabled else "fixed_quantity", "order_qty": runtime.settings.order_qty,
        "max_position_qty": runtime.settings.max_position_qty,
        "additional_buy_allowed": runtime.settings.allow_additional_buy,
        "single_position_pct": min(runtime.config.risk.max_position_pct, limits.max_single_position_pct)
        if limits is not None else None,
        "total_exposure_pct": limits.max_total_exposure_pct if limits is not None else None,
        "order_amount_usd": min(runtime.config.risk.max_order_notional or float("inf"), limits.max_order_notional)
        if limits is not None else None,
        "risk_per_trade_pct": min(runtime.config.risk.risk_per_trade_pct, limits.risk_per_trade_pct)
        if limits is not None else None,
        "daily_loss_pct": min(runtime.settings.max_daily_loss_rate / 100, limits.max_daily_loss_pct)
        if limits is not None else None,
        "fixed_stop_loss_pct": runtime.config.strategy.stop_loss_pct,
        "precedence": "all_gates_apply;strictest_limit_wins",
        "sources": [str(runtime.app_dir / "config.operating.json"),
                    str(runtime.app_dir / "trading_config.json"), str(runtime.paths.ai_config_path),
                    str(runtime.paths.spec_dir / f"{STRATEGY_ID}-{STRATEGY_VERSION}.json")],
        "reference_single_position_limit": 62.91 * 0.05,
        "reference_20_61_one_share_allowed": 20.61 <= 62.91 * 0.05,
    }
    conditions: JsonObject = {
        "build_id": BUILD_ID, "executable": str(runtime.executable),
        "executable_sha256": binding.executable_sha256,
        "account_masked": "****" + runtime.config.kis.account_no[-4:],
        "account_binding": binding.account_digest,
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "strategy_digest": SPEC_DIGEST, "risk": asdict(runtime.config.risk),
        "automatic_limits": asdict(limits) if limits is not None else None,
        "effective_limits": effective,
        "daily_loss_gui_pct": runtime.settings.max_daily_loss_rate,
        "fee_review_confirmed": fee_confirmed(runtime),
        "fee_estimate_source": "account_linked_user_reviewed_schedule" if fee_confirmed(runtime) else "unverified_planning_assumption",
        "config_source": str(runtime.app_dir / "config.operating.json"),
        "settings_source": str(runtime.app_dir / "trading_config.json"),
        "account": account, "position_count": held, "open_order_count": pending,
        "binding": asdict(binding), "blockers": [value for value in blockers],
        "confirmation_phrase": LIVE_SESSION_CONFIRMATION,
        "real_fill_validation": "not_performed",
    }
    digest = hashlib.sha256(json.dumps(conditions, sort_keys=True).encode()).hexdigest()
    return {**conditions, "review_digest": digest, "checked_at": checked.isoformat(),
            "account_checked_at": checked.isoformat(),
            "status": "ready_for_explicit_approval" if not blockers else "blocked",
            "approval_issued": False, "submitted_order": False}
