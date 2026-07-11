from __future__ import annotations

from ..models import AccountSnapshot, Position
from .common import JsonObject, _first_float, _format_price


class KISAccountMixin:
    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        """Return a conservative USD account snapshot from KIS overseas balance."""

        payload = self._inquire_balance(refresh=refresh)
        summary = payload.get("output2") or {}
        if isinstance(summary, list):
            summary = summary[0] if summary else {}
        cash = _first_float(
            summary,
            "frcr_dncl_amt_2",
            "frcr_dncl_amt",
            "ord_psbl_cash",
            "ovrs_ord_psbl_amt",
            "frcr_buy_amt_smtl1",
            "frcr_buy_amt_smtl2",
            "cash",
            default=0.0,
        )
        equity = _first_float(
            summary,
            "tot_evlu_pfls_amt",
            "ovrs_tot_pfls",
            "tot_asst_amt",
            default=cash,
        )
        buying_power = _first_float(
            summary,
            "ovrs_ord_psbl_amt",
            "ord_psbl_cash",
            default=cash,
        )
        return AccountSnapshot(cash=cash, equity=equity or cash, buying_power=buying_power)

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        """Return open KIS overseas stock positions keyed by symbol."""

        payload = self._inquire_balance(refresh=refresh)
        rows = payload.get("output1") or []
        if isinstance(rows, dict):
            rows = [rows]

        positions: dict[str, Position] = {}
        for item in rows:
            symbol = str(item.get("ovrs_pdno") or item.get("pdno") or "").upper()
            qty = _first_float(item, "ovrs_cblc_qty", "cblc_qty", "qty", default=0.0)
            if not symbol or qty <= 0:
                continue
            positions[symbol] = Position(
                symbol=symbol,
                qty=qty,
                market_value=_first_float(
                    item,
                    "ovrs_stck_evlu_amt",
                    "frcr_evlu_amt2",
                    "evlu_amt",
                    default=0.0,
                ),
                avg_entry_price=_first_float(
                    item,
                    "pchs_avg_pric",
                    "avg_unpr3",
                    "avg_entry_price",
                    default=0.0,
                ),
            )
        return positions

    def get_overseas_buying_power(
        self,
        symbol: str,
        order_price: float | None = None,
    ) -> float:
        """Return KIS symbol-specific overseas buying power in account currency."""

        price = order_price if order_price and order_price > 0 else self.get_latest_price(symbol)
        payload = self._request(
            "GET",
            "/uapi/overseas-stock/v1/trading/inquire-psamount",
            tr_id="VTTS3007R" if self.credentials.paper else "TTTS3007R",
            params={
                "CANO": self.credentials.account_no,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "OVRS_EXCG_CD": self.credentials.order_exchange_code,
                "OVRS_ORD_UNPR": _format_price(price),
                "ITEM_CD": symbol,
            },
        )
        output = payload.get("output") or {}
        if isinstance(output, list):
            output = output[0] if output else {}

        buying_power = _first_float(
            output,
            "ovrs_ord_psbl_amt",
            "frcr_ord_psbl_amt1",
            "frcr_ord_psbl_amt2",
            "ord_psbl_frcr_amt",
            "ord_psbl_cash",
            "max_ord_psbl_amt",
            "ord_psbl_amt",
            default=0.0,
        )
        possible_qty = _first_float(
            output,
            "ord_psbl_qty",
            "max_ord_psbl_qty",
            default=0.0,
        )
        if buying_power <= 0 and possible_qty > 0 and price > 0:
            buying_power = possible_qty * price
        return buying_power

    def _inquire_balance(self, refresh: bool = False) -> JsonObject:
        if self._balance_payload is not None and not refresh:
            return self._balance_payload
        self._balance_payload = self._request(
            "GET",
            "/uapi/overseas-stock/v1/trading/inquire-balance",
            tr_id="VTTS3012R" if self.credentials.paper else "TTTS3012R",
            params={
                "CANO": self.credentials.account_no,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "OVRS_EXCG_CD": self.credentials.order_exchange_code,
                "TR_CRCY_CD": self.credentials.currency,
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
        return self._balance_payload
