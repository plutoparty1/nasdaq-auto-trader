from __future__ import annotations

from math import floor, isfinite

from ..models import OrderRequest
from ..live_canary_lease import broker_submission_guard
from .common import BrokerOrderError, JsonObject, _format_price


class KISOrderMixin:
    def submit_order(self, order: OrderRequest) -> JsonObject:
        """Submit a KIS overseas stock order after converting to whole shares."""

        price = (
            order.limit_price
            if order.limit_price is not None and order.limit_price > 0
            else self.get_latest_price(order.symbol)
        )
        if not isfinite(price) or price <= 0:
            raise BrokerOrderError("KIS order price must be finite and positive")
        qty = order.qty if order.qty is not None else floor((order.notional or 0) / price)
        if not isfinite(qty):
            raise BrokerOrderError("KIS order quantity must be finite")
        qty = floor(qty)
        if qty <= 0:
            raise BrokerOrderError("KIS orders require at least one whole share")
        if order.side == "buy":
            required_cash = price * qty
            account = self.get_account(refresh=True)
            buying_power = self.get_overseas_buying_power(order.symbol, price)
            if not isfinite(account.cash) or account.cash < required_cash:
                raise BrokerOrderError("KIS buy exceeds deposited cash")
            if not isfinite(buying_power) or buying_power < required_cash:
                raise BrokerOrderError("KIS buy exceeds buying power")

        tr_id = self._order_tr_id(order.side)
        body = {
            "CANO": self.credentials.account_no,
            "ACNT_PRDT_CD": self.credentials.account_product_code,
            "OVRS_EXCG_CD": self.credentials.order_exchange_code,
            "PDNO": order.symbol,
            "ORD_QTY": str(qty),
            "OVRS_ORD_UNPR": _format_price(price),
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "SLL_TYPE": "00" if order.side == "sell" else "",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00",
        }
        with broker_submission_guard(
            self._broker_lease_path,
            self.account_fingerprint,
            order.side,
            self._broker_live_lease,
        ):
            return self._request(
                "POST",
                "/uapi/overseas-stock/v1/trading/order",
                tr_id=tr_id,
                body=body,
            )

    def _order_tr_id(self, side: str) -> str:
        if side == "buy":
            return "VTTT1002U" if self.credentials.paper else "TTTT1002U"
        if side == "sell":
            return "VTTT1006U" if self.credentials.paper else "TTTT1006U"
        raise BrokerOrderError("KIS order side must be buy or sell")
