from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, tzinfo
from pathlib import Path

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.broker import KISCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_settings import TradingSettings
from nasdaq_auto_trader.production_runtime import ProductionRuntime
from nasdaq_auto_trader.production_service import ProductionService


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ProductionService]:
    app = tmp_path / "app"
    app.mkdir()
    executable = app / "fake.exe"
    executable.write_bytes(b"sandbox-build")
    config = AppConfig(mode="live", broker="kis", allow_live_trading=True,
                       live_environment_authorized=True,
                       kis=KISCredentials("fake-key", "fake-secret", "00000000", paper=False))
    settings = TradingSettings(auto_symbol_selection_enabled=True,
                                live_trading=True, dry_run=False)
    runtime = ProductionRuntime(app, tmp_path / "original", executable, config, settings,
                                 StrategyArtifactPaths.from_root(app / "artifacts"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "isolated"))
    instance = ProductionService(runtime)
    monkeypatch.setattr(instance, "preflight", lambda: {
        "status": "ready_for_explicit_approval", "review_digest": "test-review",
        "account": {"cash": 1000.0, "equity": 1000.0, "buying_power": 1000.0},
        "blockers": [],
    })
    yield instance
    instance.shutdown()


def test_opening_service_is_paused_without_authority(service: ProductionService) -> None:
    # Given: the formal operating service has only been opened.
    # When: its operating state is inspected.
    state = service.status()
    # Then: opening never starts orders or creates an approval.
    assert state["status"] == "paused"
    assert state["submission_enabled"] is False
    assert not service.store.path.exists()
    assert not service.runtime.receipt_path.exists()


def test_live_start_requires_current_approval_before_client_creation(
    service: ProductionService, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: no approval and a client constructor that must never be reached.
    def forbidden_client(*args: str, **kwargs: bool) -> None:
        raise AssertionError("network client constructed before approval")
    monkeypatch.setattr("nasdaq_auto_trader.production_checks.make_client", forbidden_client)
    # When: the user requests live start.
    result = service.start_live()
    # Then: missing approval blocks start without reaching KIS construction.
    assert result["reason"] == "production_approval_required"
    assert service.controller.state == "paused"


def test_entry_pause_retains_protective_monitoring(service: ProductionService) -> None:
    # Given: an already running sandbox operation.
    service.controller.state = "running"
    service.gate.set_submission_enabled(True)
    # When: only new entries are stopped.
    result = service.stop_entries()
    # Then: cycles and approved protective sales remain possible.
    assert result["status"] == "entries_paused"
    assert service.controller.state == "running"
    assert service.gate.entries_enabled is False
    assert service.gate.operating_reason("sell") == ""


def test_full_shutdown_blocks_all_orders_and_stops_cycles(service: ProductionService) -> None:
    # Given: a running sandbox operation with authority enabled.
    service.controller.state = "running"
    service.gate.set_submission_enabled(True)
    # When: the user requests full shutdown.
    result = service.shutdown()
    # Then: no orders or future cycles run, and no broker cleanup is performed.
    assert result["status"] == "stopped"
    assert service.controller.state == "stopped"
    assert service.gate.submission_enabled is False
    assert service.factory.client is None
    assert result["orders_cancelled"] == 0


def test_simulation_starts_without_live_authority(service: ProductionService) -> None:
    # Given: no approval in the isolated service.
    # When: the user starts ordinary read-only simulation.
    result = service.start_simulation()
    # Then: it runs dry and leaves live authorization locked.
    assert result["mode"] == "dry_run"
    assert service.controller.config.mode == "dry_run"
    assert service.gate.submission_enabled is False
    assert service.controller.session_store.path != service.runtime.session_path


def test_approved_start_binds_actual_kis_client_to_shared_lease_without_orders(
    service: ProductionService, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: only a sandbox service and an already-validated test approval seam.
    from nasdaq_auto_trader.brokers.kis_client import KISClient
    from nasdaq_auto_trader.live_canary_lease import BrokerLeaseError

    class TestClock:
        @staticmethod
        def now(_zone: tzinfo | None = None) -> datetime:
            return datetime(2026, 10, 13, 15, tzinfo=UTC)

    monkeypatch.setattr("nasdaq_auto_trader.production_service.datetime", TestClock)
    monkeypatch.setattr("nasdaq_auto_trader.production_service.conflicting_processes", lambda _runtime: [])
    monkeypatch.setattr(service.gate, "reason", lambda *_args: "")
    # When: explicit start constructs the actual KIS client and acquires the shared lease.
    result = service.start_live()
    # Then: the future real path is connected, but start sends no order or approval request.
    assert result["mode"] == "live"
    assert result["submitted_order"] is False
    client = service.factory.client
    assert isinstance(client, KISClient)
    assert client._broker_lease_path == service.runtime.original_data / "live_canary" / "broker-live-owner.lock"
    lease = client._broker_live_lease
    assert lease is not None
    lease.assert_allowed(client._broker_lease_path, client.account_fingerprint, "buy")
    assert not service.store.path.exists()
    assert not service.runtime.receipt_path.exists()
    service.shutdown()
    with pytest.raises(BrokerLeaseError, match="broker_live_lease_inactive"):
        lease.assert_allowed(client._broker_lease_path, client.account_fingerprint, "buy")


def test_resume_entries_uses_same_session_without_new_approval(
    service: ProductionService, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an approved running sandbox session with entries paused.
    service.controller.state = "running"
    service.factory.mode = "live"
    service.gate.set_submission_enabled(True)
    service.gate.set_entries_enabled(False)
    monkeypatch.setattr(service.gate, "reason", lambda *_args: "")
    original = service.controller.session_state
    # When: the existing start button resumes entries within the current approval.
    result = service.start_live()
    # Then: it retains baseline/state and grants no new approval.
    assert result["entries_resumed"] is True
    assert service.controller.session_state is original
    assert service.gate.entries_enabled is True
    assert not service.store.path.exists()


def test_ongoing_session_cannot_sell_foreign_position(service: ProductionService) -> None:
    # Given: an operating session whose foreign holding has no production receipt.
    from nasdaq_auto_trader.models import OrderRequest
    service.gate.set_submission_enabled(True)
    # When: its mandatory per-submission ownership checker sees a sell.
    reason = service.gate.order_reason(OrderRequest("FOREIGN", "sell", qty=1))
    # Then: even an ongoing session cannot adopt and sell that holding.
    assert reason == "production_position_not_owned"


def test_ongoing_session_keeps_owned_protective_sell(
    service: ProductionService, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an exact local own-order receipt and matching read-only fill/position data.
    from nasdaq_auto_trader.brokers.kis_reconciliation import KISOrderHistory
    from nasdaq_auto_trader.live_authorization import broker_authorization_digest
    from nasdaq_auto_trader.models import OrderRequest, Position
    from nasdaq_auto_trader.production_ownership import ProductionSessionStore
    from nasdaq_auto_trader.session_claims import (
        AcceptedBuyReceipt,
        ClaimStatus,
        SignalKey,
    )

    store = ProductionSessionStore(service.runtime.session_path,
                                   broker_authorization_digest(service.runtime.config))
    key = SignalKey("2026-10-13", "s", "v", "TEST", "buy", "bar")
    assert store.claim(key).granted
    store.complete(key, ClaimStatus.SUBMITTED, AcceptedBuyReceipt("sandbox-order", "TEST", "2026-10-13", 0))

    class Reader:
        def list_positions(self, refresh: bool = False) -> dict[str, Position]:
            return {"TEST": Position("TEST", 1, 19, 20.61)}

        def list_order_history(self, start: str, end: str) -> tuple[KISOrderHistory, ...]:
            return (KISOrderHistory("sandbox-order", "TEST", "buy", 1, 1, 20.61, "filled",
                                    datetime(2026, 10, 13, 15, tzinfo=UTC)),)

    monkeypatch.setattr("nasdaq_auto_trader.production_checks.make_client", lambda *_args, **_kwargs: Reader())
    service.gate.set_submission_enabled(True)
    service.gate.set_entries_enabled(False)
    # When: a loss-making protective sell is checked during the entry pause.
    reason = service.gate.order_reason(OrderRequest("TEST", "sell", qty=1))
    # Then: ownership is verified and no profitability requirement blocks protection.
    assert reason == ""
