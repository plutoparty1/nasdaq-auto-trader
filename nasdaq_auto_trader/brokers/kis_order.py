from __future__ import annotations

from math import floor

from ..models import OrderRequest
from .common import BrokerOrderError, JsonObject, _format_price


class KISOrderMixin:
    def submit_order(self, order: OrderRequest) -> JsonObject:
        """Submit a KIS overseas stock order after converting to whole shares."""

        price = (
            order.limit_price
            if order.limit_price is not None and order.limit_price > 0
            else self.get_latest_price(order.symbol)
        )
        qty = order.qty if order.qty is not None else floor((order.notional or 0) / price)
        qty = floor(qty)
        if qty <= 0:
            raise BrokerOrderError("KIS orders require at least one whole share")

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
