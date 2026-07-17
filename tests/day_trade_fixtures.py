from __future__ import annotations

from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest


class FakeDayTradeClient:
    def __init__(self):
        self.buying_power_calls = []
        self.account_calls = []
        self.submitted_orders = []
        self.cash = 64.0
        self.details = {
            "GOOD": {
                "name": "Good Test Corp",
                "last": "10.00",
                "base": "9.80",
                "high": "10.50",
                "low": "9.70",
                "tvol": "1000000",
            },
            "WIDE": {
                "name": "Wide Spread Corp",
                "last": "10.00",
                "base": "9.90",
                "high": "10.30",
                "low": "9.80",
                "tvol": "1000000",
            },
            "LOWVOL": {
                "name": "Low Volume Corp",
                "last": "12.00",
                "base": "11.90",
                "high": "12.10",
                "low": "11.80",
                "tvol": "1000",
            },
            "EXPENSIVE": {
                "name": "Expensive Corp",
                "last": "70.00",
                "base": "69.00",
                "high": "71.00",
                "low": "68.00",
                "tvol": "1000000",
            },
        }
        self.quotes = {
            "GOOD": {
                "pbid1": "9.99",
                "pask1": "10.01",
                "vbid1": "1000",
                "vask1": "1100",
            },
            "WIDE": {
                "pbid1": "9.50",
                "pask1": "10.50",
                "vbid1": "1000",
                "vask1": "1100",
            },
            "LOWVOL": {
                "pbid1": "11.99",
                "pask1": "12.01",
                "vbid1": "1000",
                "vask1": "1100",
            },
            "EXPENSIVE": {
                "pbid1": "69.99",
                "pask1": "70.01",
                "vbid1": "1000",
                "vask1": "1100",
            },
        }

    def get_price_detail(self, symbol):
        return self.details[symbol]

    def get_best_quote(self, symbol):
        return self.quotes[symbol]

    def get_overseas_buying_power(self, symbol, order_price=None):
        self.buying_power_calls.append((symbol, order_price))
        return 64.0

    def get_account(self, refresh=False):
        self.account_calls.append(refresh)
        return AccountSnapshot(cash=self.cash, equity=self.cash, buying_power=64.0)

    def submit_order(self, order):
        self.submitted_orders.append(order)
        return {"rt_cd": "0", "ODNO": "123"}
