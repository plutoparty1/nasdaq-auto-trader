from __future__ import annotations

from tests.config_engine_fixtures import *
import os
from unittest.mock import patch


class ConfigEngineKISTests(unittest.TestCase):
    def test_default_kis_token_cache_uses_application_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}):
                client = KISClient(
                    KISCredentials(
                        app_key="app",
                        app_secret="secret",
                        account_no="12345678",
                        paper=False,
                    )
                )
                expected = (
                    Path(temp_dir)
                    / "NasdaqAutoTrader"
                    / "runtime"
                    / ".kis_token.json"
                )

        self.assertEqual(client._token_cache_path, expected)
    def test_kis_account_uses_present_balance_deposit_and_balance_positions(self):
        test_case = self

        class FakeKISClient(KISClient):
            def __init__(self):
                super().__init__(
                    KISCredentials(
                        app_key="app",
                        app_secret="secret",
                        account_no="12345678",
                        paper=False,
                    )
                )

            def _request(self, method, path, tr_id, params=None, body=None):
                if path.endswith("/inquire-present-balance"):
                    test_case.assertEqual(tr_id, "CTRP6504R")
                    test_case.assertEqual(params["WCRC_FRCR_DVSN_CD"], "02")
                    test_case.assertEqual(params["NATN_CD"], "840")
                    return {
                        "rt_cd": "0",
                        "output2": [
                            {"crcy_cd": "JPY", "frcr_dncl_amt_2": "9000.00"},
                            {"crcy_cd": "USD", "frcr_dncl_amt_2": "40.00"},
                        ],
                        "output3": {"tot_asst_amt": "100000.00"},
                    }
                test_case.assertEqual(
                    path,
                    "/uapi/overseas-stock/v1/trading/inquire-balance",
                )
                return {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "ovrs_pdno": "HIVE",
                            "ovrs_cblc_qty": "2",
                            "ovrs_stck_evlu_amt": "8.20",
                            "pchs_avg_pric": "3.50",
                        }
                    ],
                    "output2": {"tot_evlu_pfls_amt": "2.50"},
                }

        client = FakeKISClient()

        account = client.get_account()
        positions = client.list_positions()

        self.assertEqual(account.cash, 40.00)
        self.assertEqual(account.equity, 40.00)
        self.assertEqual(account.buying_power, 40.00)
        self.assertEqual(positions["HIVE"].qty, 2)
        self.assertEqual(positions["HIVE"].market_value, 8.20)

    def test_kis_balance_does_not_treat_orderable_amount_as_deposited_cash(self):
        class FakeKISClient(KISClient):
            def _request(self, method, path, tr_id, params=None, body=None):
                return {
                    "rt_cd": "0",
                    "output1": [],
                    "output2": {
                        "ovrs_ord_psbl_amt": "1000.00",
                        "cash": "1000.00",
                        "tot_asst_amt": "1000.00",
                    },
                }

        client = FakeKISClient(
            KISCredentials(
                app_key="app",
                app_secret="secret",
                account_no="12345678",
                paper=False,
            )
        )

        account = client.get_account()

        self.assertEqual(account.cash, 0.0)
        self.assertEqual(account.buying_power, 0.0)

    def test_kis_buying_power_uses_psamount_endpoint(self):
        class FakeKISClient(KISClient):
            def __init__(self):
                super().__init__(
                    KISCredentials(
                        app_key="app",
                        app_secret="secret",
                        account_no="12345678",
                        paper=False,
                    )
                )
                self.calls = []

            def _request(self, method, path, tr_id, params=None, body=None):
                self.calls.append((method, path, tr_id, params))
                return {
                    "rt_cd": "0",
                    "output": {
                        "frcr_ord_psbl_amt1": "64.50",
                        "ord_psbl_qty": "16",
                    },
                }

        client = FakeKISClient()

        buying_power = client.get_overseas_buying_power("HIVE", 3.9)

        self.assertEqual(buying_power, 64.50)
        method, path, tr_id, params = client.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(path, "/uapi/overseas-stock/v1/trading/inquire-psamount")
        self.assertEqual(tr_id, "TTTS3007R")
        self.assertEqual(params["ITEM_CD"], "HIVE")
        self.assertEqual(params["OVRS_ORD_UNPR"], "3.9")

    def test_kis_token_cache_reuses_unexpired_token(self):
        class FakeKISClient(KISClient):
            def _open_json(self, request, label):
                raise AssertionError("token endpoint should not be called")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / ".kis_token.json"
            client = FakeKISClient(
                KISCredentials(
                    app_key="app",
                    app_secret="secret",
                    account_no="12345678",
                    paper=False,
                ),
                token_cache_path=cache_path,
            )
            cache_path.write_text(
                json.dumps(
                    {
                        "cache_key": client._token_cache_key(),
                        "access_token": "cached-token",
                        "expires_at": (
                            datetime.now(timezone.utc) + timedelta(hours=1)
                        ).isoformat(),
                    }
                ),
                encoding="utf-8",
            )

            client._ensure_token()

        self.assertEqual(client._access_token, "cached-token")

    def test_kis_order_payload_converts_notional_to_whole_share_limit_order(self):
        class FakeKISClient(KISClient):
            def __init__(self):
                super().__init__(
                    KISCredentials(
                        app_key="app",
                        app_secret="secret",
                        account_no="12345678",
                        paper=True,
                    )
                )
                self.calls = []

            def get_latest_price(self, symbol):
                self.calls.append(("price", symbol))
                return 101.25

            def get_account(self, refresh=False):
                return AccountSnapshot(cash=250, equity=250, buying_power=250)

            def get_overseas_buying_power(self, symbol, order_price=None):
                return 250.0

            def _request(self, method, path, tr_id, params=None, body=None):
                self.calls.append((method, path, tr_id, body))
                return {"rt_cd": "0", "output": {"ODNO": "1"}}

        client = FakeKISClient()

        response = client.submit_order(
            OrderRequest(symbol="AAPL", side="buy", notional=250.0)
        )

        self.assertEqual(response["rt_cd"], "0")
        self.assertEqual(client.calls[-1][2], "VTTT1002U")
        body = client.calls[-1][3]
        self.assertEqual(body["PDNO"], "AAPL")
        self.assertEqual(body["ORD_QTY"], "2")
        self.assertEqual(body["OVRS_ORD_UNPR"], "101.25")
        self.assertEqual(body["ORD_DVSN"], "00")

    def test_kis_order_payload_uses_explicit_limit_price_for_qty_order(self):
        class FakeKISClient(KISClient):
            def __init__(self):
                super().__init__(
                    KISCredentials(
                        app_key="app",
                        app_secret="secret",
                        account_no="12345678",
                        paper=False,
                    )
                )
                self.calls = []

            def get_latest_price(self, symbol):
                raise AssertionError("explicit limit order should not reprice")

            def get_account(self, refresh=False):
                return AccountSnapshot(cash=64, equity=64, buying_power=64)

            def get_overseas_buying_power(self, symbol, order_price=None):
                return 64.0

            def _request(self, method, path, tr_id, params=None, body=None):
                self.calls.append((method, path, tr_id, body))
                return {"rt_cd": "0", "output": {"ODNO": "1"}}

        client = FakeKISClient()

        response = client.submit_order(
            OrderRequest(
                symbol="HIVE",
                side="buy",
                type="limit",
                qty=1,
                limit_price=3.88,
            )
        )

        self.assertEqual(response["rt_cd"], "0")
        self.assertEqual(client.calls[-1][2], "TTTT1002U")
        body = client.calls[-1][3]
        self.assertEqual(body["PDNO"], "HIVE")
        self.assertEqual(body["ORD_QTY"], "1")
        self.assertEqual(body["OVRS_ORD_UNPR"], "3.88")
