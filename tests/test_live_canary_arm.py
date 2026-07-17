from __future__ import annotations

import hashlib
import unittest
from datetime import UTC, datetime, timedelta

from nasdaq_auto_trader.live_canary_arm import ArmValidationContext, parse_arm_envelope, validate_arm_envelope
from nasdaq_auto_trader.live_canary_identity import account_fingerprint
from nasdaq_auto_trader.live_canary_policy import CANARY_POLICY


class LiveCanaryArmTests(unittest.TestCase):
    def test_arm_requires_every_current_binding(self) -> None:
        # Given: an arm for one real KIS account, market date, policy, executable, and Windows user.
        now = datetime(2026, 7, 17, tzinfo=UTC)
        sid_hash = hashlib.sha256(b"S-1-5-21-test").hexdigest()
        envelope = parse_arm_envelope({
            "schema_version": "1", "market_date": "2026-07-17",
            "account_fingerprint": account_fingerprint("12345678", "01"), "product": "01",
            "base_url": "https://openapi.koreainvestment.com:9443", "executable_sha256": "a" * 64,
            "policy_digest": CANARY_POLICY.digest, "windows_sid_sha256": sid_hash, "state_nonce": "nonce-123",
            "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=5)).isoformat(),
        })

        # When: validating the exact environment.
        validate_arm_envelope(envelope, ArmValidationContext(
            market_date="2026-07-17", account_fingerprint=account_fingerprint("12345678", "01"),
            product="01", base_url="https://openapi.koreainvestment.com:9443", executable_sha256="a" * 64,
            policy_digest=CANARY_POLICY.digest, windows_sid_sha256=sid_hash, now=now,
        ))

        # Then: every independently changed binding is rejected.
        with self.assertRaises(Exception):
            validate_arm_envelope(envelope, ArmValidationContext(
                market_date="2026-07-18", account_fingerprint=account_fingerprint("12345678", "01"),
                product="01", base_url="https://openapi.koreainvestment.com:9443", executable_sha256="a" * 64,
                policy_digest=CANARY_POLICY.digest, windows_sid_sha256=sid_hash, now=now,
            ))
