import pytest

from nasdaq_auto_trader.production_service import ProductionService
from tests.test_production_service import service


def test_prepare_refuses_to_change_running_live(service: ProductionService) -> None:
    # Given: the service already operates live.
    service.controller.state = "running"
    service.factory.mode = "live"
    # When: another proposal is requested.
    result = service.prepare_start()
    # Then: the live service remains running without new approval.
    assert result["status"] == "blocked"
    assert "live_operation_already_running" in result["blockers"]
    assert service.controller.state == "running"


def test_fee_checkbox_cannot_create_evidence(service: ProductionService) -> None:
    # Given: no account-linked numeric fee schedule exists.
    # When: the old checkbox API is invoked.
    result = service.configure_fees(True)
    # Then: it blocks without writing fake evidence.
    assert result["status"] == "blocked"
    assert not (service.runtime.app_dir / "fee-review.json").exists()


def test_prepare_stops_only_own_simulation_without_approval(service: ProductionService, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: only this service's dry-run loop is running.
    base = service.runtime
    monkeypatch.setattr("nasdaq_auto_trader.production_start_flow.load_runtime", lambda *args: base)
    service.start_simulation()
    # When: the formal start review is prepared.
    result = service.prepare_start()
    # Then: its dry run stops and review cannot silently issue approval.
    assert service.controller.state == "stopped"
    assert "automatic_plan" in result
    assert "approval_window" in result
    assert not service.store.path.exists()


def test_confirm_without_review_cannot_issue_approval(service: ProductionService) -> None:
    # Given: the user has not reviewed a proposal.
    # When: confirmation is attempted with an unrelated digest.
    result = service.confirm_start("I ACKNOWLEDGE LIVE TRADING", "not-reviewed")
    # Then: no approval or start occurs.
    assert result["status"] == "blocked"
    assert not service.store.path.exists()


def test_fee_input_requires_account_numeric_provenance(service: ProductionService) -> None:
    from nasdaq_auto_trader.production_fees import FeeScheduleInput, load_fee_schedule
    # Given: a future user submits the actual account schedule in a sandbox.
    profile = FeeScheduleInput(.001, .01, .00001, "KIS USD account schedule, effective 2026-10-13, no discount", effective_from="2026-01-01", effective_to="2026-12-31")
    # When: only that reviewed fee profile is stored.
    result = service.configure_fee_profile(profile)
    # Then: evidence is account-bound, without issuing approval.
    assert result["status"] == "draft_changed"
    assert load_fee_schedule(service.runtime) is not None
    assert not service.store.path.exists()


def test_fee_edit_cannot_interrupt_own_live_protection(service: ProductionService) -> None:
    from nasdaq_auto_trader.production_fees import FeeScheduleInput
    # Given: an approved live loop is already monitoring protective exits.
    service.controller.state = "running"
    service.factory.mode = "live"
    service.gate.set_submission_enabled(True)
    # When: a draft fee change is requested during that loop.
    result = service.configure_fee_profile(FeeScheduleInput(.001, 0, 0, "actual schedule"))
    # Then: the rejected edit leaves current submission authority unchanged.
    assert result["status