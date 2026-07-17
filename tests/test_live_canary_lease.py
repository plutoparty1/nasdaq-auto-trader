from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.live_canary_lease import (
    BrokerLeaseError,
    BrokerLiveLease,
    broker_submission_guard,
)
from nasdaq_auto_trader.brokers.kis_client import KISClient, KISCredentials
from nasdaq_auto_trader.brokers.kis_reconciliation import KISCancelOrder
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest


class LeaseAwareKISClient(KISClient):
    def __init__(self, lease_path: Path) -> None:
        super().__init__(KISCredentials("app", "secret", "12345678"))
        self._broker_lease_path = lease_path
        self.posts = 0

    def get_latest_price(self, symbol: str) -> float:
        return 10.0

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        return AccountSnapshot(cash=20.0, equity=20.0, buying_power=20.0)

    def get_overseas_buying_power(self, symbol: str, price: float) -> float:
        return 20.0

    def _request(self, method, path, tr_id, params=None, body=None, tr_cont=""):
        if method == "POST":
            self.posts += 1
        return {"output": {"ODNO": "9001"}}


class BrokerLiveLeaseTests(unittest.TestCase):
    def test_active_canary_lease_blocks_unowned_broker_submission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broker-live-owner.lock"

            with BrokerLiveLease.acquire(path, "account-a", frozenset({"buy", "sell"})):
                with self.assertRaises(BrokerLeaseError) as raised:
                    with broker_submission_guard(path, "account-a", "buy"):
                        self.fail("unowned submission entered guarded section")

        self.assertEqual(raised.exception.reason, "broker_live_owner_active")

    def test_owned_lease_permits_only_its_account_and_allowed_side(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broker-live-owner.lock"

            with BrokerLiveLease.acquire(path, "account-a", frozenset({"sell"})) as lease:
                with broker_submission_guard(path, "account-a", "sell", lease):
                    permitted = True
                with self.assertRaises(BrokerLeaseError) as side_error:
                    with broker_submission_guard(path, "account-a", "buy", lease):
                        self.fail("buy entered exit-only lease")
                with self.assertRaises(BrokerLeaseError) as account_error:
                    with broker_submission_guard(path, "account-b", "sell", lease):
                        self.fail("different account entered lease")

        self.assertTrue(permitted)
        self.assertEqual(side_error.exception.reason, "broker_live_side_not_allowed")
        self.assertEqual(account_error.exception.reason, "broker_live_account_mismatch")

    def test_released_lease_allows_legacy_submission_guard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broker-live-owner.lock"
            with BrokerLiveLease.acquire(path, "account-a", frozenset({"buy", "sell"})):
                pass

            with broker_submission_guard(path, "account-a", "buy"):
                permitted = True

        self.assertTrue(permitted)

    def test_released_lease_object_cannot_be_reused_as_authority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broker-live-owner.lock"
            with BrokerLiveLease.acquire(path, "account-a", frozenset({"buy"})) as lease:
                pass

            with self.assertRaises(BrokerLeaseError) as raised:
                with broker_submission_guard(path, "account-a", "buy", lease):
                    self.fail("released lease was reused")

        self.assertEqual(raised.exception.reason, "broker_live_lease_inactive")

    def test_kis_submit_and_cancel_cannot_bypass_active_canary_lease(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broker-live-owner.lock"
            client = LeaseAwareKISClient(path)

            with BrokerLiveLease.acquire(path, client.account_fingerprint, frozenset({"buy", "sell"})):
                with self.assertRaises(BrokerLeaseError):
                    client.submit_order(OrderRequest("AAPL", "buy", qty=1, limit_price=10.0))
                with self.assertRaises(BrokerLeaseError):
                    client.cancel_order(KISCancelOrder("9001", "AAPL", "buy", 1, 10.0))

        self.assertEqual(client.posts, 0)

    def test_kis_owned_exit_only_lease_allows_sell_but_blocks_buy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broker-live-owner.lock"
            client = LeaseAwareKISClient(path)

            with BrokerLiveLease.acquire(path, client.account_fingerprint, frozenset({"sell"})) as lease:
                client.bind_live_lease(lease)
                client.submit_order(OrderRequest("AAPL", "sell", qty=1, limit_price=10.0))
                with self.assertRaises(BrokerLeaseError):
                    client.submit_order(OrderRequest("AAPL", "buy", qty=1, limit_price=10.0))
                client.cancel_order(KISCancelOrder("9001", "AAPL", "sell", 1, 10.0))

        self.assertEqual(client.posts, 2)


if __name__ == "__main__":
    unittest.main()
