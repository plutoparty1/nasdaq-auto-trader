from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nasdaq_auto_trader.broker import KISCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_settings import TradingSettings
from nasdaq_auto_trader.live_authorization import LiveAuthorizationEnvelope
from nasdaq_auto_trader.live_authorization_store import LiveAuthorizationStore


def test_production_order_requires_separate_approval_when_legacy_exists(tmp_path: Path) -> None:
    # Given: an existing authorization without the new build-bound receipt.
    from nasdaq_auto_trader.production_authorization import ProductionOrderGate

    executable = tmp_path / "app.exe"
    executable.write_bytes(b"build-one")
    store = LiveAuthorizationStore(tmp_path / "legacy.json")
    gate = ProductionOrderGate(executable, tmp_path / "approval.json", store)
    # When: the formal production order path checks approval.
    reason = gate.reason(_config(), TradingSettings(), _now())
    # Then: old approval cannot grant access to the new build.
    assert reason == "production_approval_required"


@pytest.mark.parametrize("change,expected", [
    ("none", ""),
    ("build", "production_build_mismatch"),
    ("account", "production_account_mismatch"),
    ("config", "production_config_mismatch"),
    ("settings", "production_settings_mismatch"),
    ("date", "production_approval_expired"),
    ("close", "outside_regular_session"),
    ("legacy", "production_authorization_mismatch"),
])
def test_production_binding_rejects_changed_inputs_when_approved(
    tmp_path: Path, change: str, expected: str,
) -> None:
    # Given: a receipt tied to a sandbox account, executable and final settings.
    from nasdaq_auto_trader.live_authorization import broker_authorization_digest
    from nasdaq_auto_trader.production_authorization import (
        ProductionBinding,
        ProductionOrderGate,
        ProductionReceipt,
        write_production_receipt,
    )

    executable = tmp_path / "app.exe"
    executable.write_bytes(b"build-one")
    config, settings, now = _config(), TradingSettings(), _now()
    store = LiveAuthorizationStore(tmp_path / "sandbox-legacy.json")
    envelope = LiveAuthorizationEnvelope(
        "0" * 32, now.date(), 12, "builtin_ai_volatility_target", "v1", "s",
        "u", "2026-10-13", "u1", "r", "live", "l",
        broker_authorization_digest(config),
    )
    store.issue(envelope)
    path = tmp_path / "sandbox-approval.json"
    write_production_receipt(path, ProductionReceipt(
        ProductionBinding.capture(executable, config, settings),
        envelope.authorization_id, envelope.market_date.isoformat(),
    ))
    match change:
        case "build": executable.write_bytes(b"build-two")
        case "account": config = replace(config, kis=replace(config.kis, account_no="99999999"))
        case "config": config = replace(config, risk=replace(config.risk, max_position_pct=0.9))
        case "settings": settings = replace(settings, max_position_qty=2)
        case "date": now = datetime(2026, 10, 14, 15, tzinfo=UTC)
        case "close": now = datetime(2026, 10, 13, 20, tzinfo=UTC)
        case "legacy": store.issue(replace(envelope, authorization_id="1" * 32))
        case "none": pass
    gate = ProductionOrderGate(executable, path, store)
    # When: any final approval binding is checked again before submission.
    reason = gate.reason(config, settings, now)
    # Then: every mismatch is rejected with a specific reason.
    assert reason == expected


def test_production_settings_on_disk_must_match_when_memory_is_unchanged(tmp_path: Path) -> None:
    # Given: approved memory settings but a changed source configuration.
    from nasdaq_auto_trader.live_authorization import broker_authorization_digest
    from nasdaq_auto_trader.production_authorization import (
        ProductionBinding,
        ProductionOrderGate,
        ProductionReceipt,
        write_production_receipt,
    )

    executable = tmp_path / "app.exe"
    executable.write_bytes(b"sandbox-build")
    config, settings = _config(), TradingSettings()
    binding = ProductionBinding.capture(executable, config, settings)
    store = LiveAuthorizationStore(tmp_path / "sandbox-legacy.json")
    envelope = LiveAuthorizationEnvelope(
        "0" * 32, _now().date(), 12, "strategy", "v1", "s", "u", "2026-10-13",
        "u1", "r", "live", "l", broker_authorization_digest(config),
    )
    store.issue(envelope)
    path = tmp_path / "sandbox-approval.json"
    write_production_receipt(path, ProductionReceipt(binding, envelope.authorization_id, "2026-10-13"))
    gate = ProductionOrderGate(executable, path, store,
                               current_binding=lambda: replace(binding, config_digest="changed"))
    # When: submission checks the source files again.
    reason = gate.reason(config, settings, _now())
    # Then: unchanged engine memory does not hide edits on disk.
    assert reason == "production_config_source_changed"


def test_entry_pause_preserves_sell_capability_when_started(tmp_path: Path) -> None:
    # Given: operational control distinct from approval verification.
    from nasdaq_auto_trader.production_authorization import ProductionOrderGate

    gate = ProductionOrderGate(tmp_path / "unused.exe", tmp_path / "unused.json",
                               LiveAuthorizationStore(tmp_path / "sandbox-store.json"))
    assert gate.operating_reason("sell") == "production_start_required"
    gate.set_submission_enabled(True)
    gate.set_entries_enabled(False)
    # When: entries are paused without ending the monitoring session.
    reasons = (gate.operating_reason("buy"), gate.operating_reason("sell"))
    # Then: only new buys are blocked by this control; approval remains separately mandatory.
    assert reasons == ("production_entries_paused", "")


def test_formal_approval_reuses_existing_confirmation_when_unconfirmed(tmp_path: Path) -> None:
    # Given: no user confirmation and only a sandbox account/store.
    from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
    from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
    from nasdaq_auto_trader.live_session_authorization import (
        SessionAuthorizationRequest,
    )
    from nasdaq_auto_trader.production_authorization import (
        ProductionApprovalRequest,
        authorize_production_session,
    )

    executable = tmp_path / "app.exe"
    executable.write_bytes(b"sandbox-build")
    store = LiveAuthorizationStore(tmp_path / "sandbox-store.json")
    receipt = tmp_path / "sandbox-receipt.json"
    request = ProductionApprovalRequest(SessionAuthorizationRequest(
        _config(), StrategyArtifactPaths.from_root(tmp_path / "sandbox-artifacts"),
        store, NullAuditLogger(), _now(), 12, "not-approved",
    ), executable, receipt, TradingSettings())
    # When: the formal entry requests approval through the existing procedure.
    result = authorize_production_session(request)
    # Then: it writes neither a legacy approval nor a build-bound receipt.
    assert result["reason"] == "live_session_confirmation_required"
    assert not store.path.exists()
    assert not receipt.exists()


def test_strategy_file_change_invalidates_binding_when_approved(tmp_path: Path) -> None:
    # Given: a bound strategy artifact and sandbox executable.
    from nasdaq_auto_trader.production_authorization import ProductionBinding

    executable, strategy = tmp_path / "app.exe", tmp_path / "strategy.json"
    executable.write_bytes(b"sandbox-build")
    strategy.write_text("version-one", encoding="utf-8")
    before = ProductionBinding.capture(executable, _config(), TradingSettings(), artifacts=(strategy,))
    strategy.write_text("version-two", encoding="utf-8")
    # When: the strategy artifact is changed without a new approval.
    after = ProductionBinding.capture(executable, _config(), TradingSettings(), artifacts=(strategy,))
    # Then: strategy changes are detected even with the same identifier and GUI settings.
    assert after.artifacts_digest != before.artifacts_digest


def _config() -> AppConfig:
    return AppConfig(
        mode="live", broker="kis", allow_live_trading=True,
        live_environment_authorized=True,
        kis=KISCredentials("sandbox-key", "sandbox-secret", "00000000", paper=False),
    )


def _now() -> datetime:
    return datetime(2026, 10, 13, 15, tzinfo=UTC)
