from pathlib import Path

from nasdaq_auto_trader.production_fees import parse_fee_schedule


def test_boolean_confirmation_does_not_establish_verified_fees() -> None:
    # Given: the old checkbox-only record has no account-linked fee schedule.
    payload = '{"confirmed":true,"source":"user"}'
    # When: it is parsed for the current account.
    result = parse_fee_schedule(payload, "account-digest")
    # Then: approval cannot infer fee rates from a checkbox.
    assert result is None


def test_other_account_fee_schedule_cannot_be_inherited() -> None:
    # Given: a complete schedule belongs to another account.
    payload = '{"confirmed":true,"account_digest":"other","commission_rate":0.001,"minimum_fee_usd":0,"tax_rate":0.00001,"source":"broker schedule","reviewed_at":"2026-10-13T15:00:00+00:00"}'
    # When: the current account reads it.
    result = parse_fee_schedule(payload, "account-digest")
    # Then: the foreign schedule is rejected.
    assert result is None
