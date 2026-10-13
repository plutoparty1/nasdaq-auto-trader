from __future__ import annotations

import pytest

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.app_controller import AutoTradeController
from nasdaq_auto_trader.production_fees import FeeScheduleInput
from nasdaq_auto_trader.production_gui_actions import (
    approve_review,
    confirm_prepared_start,
    review_summary,
)


class Facade:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    @property
    def controller(self) -> AutoTradeController:
        raise NotImplementedError

    def preflight(self) -> JsonObject:
        return {}

    def prepare_start(self) -> JsonObject:
        return {}

    def confirm_start(self, confirmation: str, review_digest: str) -> JsonObject:
        self.calls.append((confirmation, review_digest))
        return {"status": "running"}

    def review(self) -> JsonObject:
        return {}

    def status(self) -> JsonObject:
        return {}

    def configure_fees(self, confirmed: bool) -> JsonObject:
        return {"fees_confirmed": confirmed}

    def configure_fee_profile(self, profile: FeeScheduleInput) -> JsonObject:
        return {"fee_source": profile.source}

    def authorize(self, confirmation: str, review_digest: str) -> JsonObject:
        self.calls.append((confirmation, review_digest))
        return {"status": "authorized"}

    def start_live(self) -> JsonObject:
        return {}

    def start_simulation(self) -> JsonObject:
        return {}

    def stop_entries(self) -> JsonObject:
        return {}

    def shutdown(self) -> JsonObject:
        return {}


@pytest.mark.parametrize(("confirmation", "digest", "fees"), [
    ("", "digest", True), ("approve", "", True), ("approve", "digest", False),
])
def test_no_authorization_without_explicit_review(confirmation: str, digest: str, fees: bool) -> None:
    facade = Facade()
    result = approve_review(facade, confirmation=confirmation, digest=digest, fees_confirmed=fees)
    assert result["status"] == "blocked"
    assert facade.calls == []


def test_explicit_review_is_forwarded_to_existing_authorization() -> None:
    facade = Facade()
    result = approve_review(facade, confirmation="approve", digest="build-profile-account", fees_confirmed=True)
    assert result["status"] == "authorized"
    assert facade.calls == [("approve", "build-profile-account")]


def test_blocked_review_cannot_start_even_with_confirmation() -> None:
    facade = Facade()
    result = confirm_prepared_start(facade, confirmation="approve", review={
        "review_digest": "digest", "blockers": ["actual_fees_unconfirmed"],
    })
    assert result["status"] == "blocked"
    assert facade.calls == []


def test_ready_review_uses_single_verified_start_service() -> None:
    facade = Facade()
    result = confirm_prepared_start(facade, confirmation="approve", review={
        "status": "ready_for_explicit_approval", "review_digest": "digest", "blockers": [],
    })
    assert result["status"] == "running"
    assert facade.calls == [("approve", "digest")]


def test_review_expiry_is_readable_without_opening_json() -> None:
    summary = review_summary({"approval_window": {
        "duration_hours": 12, "expires_at": "2026-10-14T00:00:00Z",
        "expiry_behavior": "expiry blocks both entries and protective sales",
    }})
    assert "12" in summary
    assert "2026-10-14 09:00:00 KST" in summary
    assert "expiry blocks both entries and protective sales" in summary
