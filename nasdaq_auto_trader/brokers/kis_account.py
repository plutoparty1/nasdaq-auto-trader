from __future__ import annotations

from math import isfinite

from ..models import AccountSnapshot, Position
from ..live_canary_policy import CANARY_POLICY
from .common import BrokerRequestError, JsonObject, _first_float, _format_price


class KISAccountMixin:
    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        """Return a conservative USD account snapshot from KIS overseas balance."""

        payload = self._inquire_present_balance(refresh=refresh)
        raw_summaries = payload.get("output2") or []
        summaries = raw_summaries if isinstance(raw_summaries, list) else [raw_summaries]
        summary = next(
            (
                item
                for item in summaries
                if isinstance(item, dict)
                and str(item.get("crcy_cd") or self.credentials.currency).upper()
                == self.credentials.currency.upper()
            ),
            {},
        )
        cash = _first_float(
            summary,
            "frcr_dncl_amt_2",
            "frcr_dncl_amt",
            default=0.0,
        )
        deposited_cash = cash if isfinite(cash) and cash > 0 else 0.0
        return AccountSnapshot(
            cash=deposited_cash,
            equity=deposited_cash,
            buying_power=deposited_cash,
        )

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        """Return open KIS overseas stock positions keyed by symbol."""

        payload = self._inquire_balance(refresh=refresh)
        rows = payload.get("output1") or []
        if isinstance(rows, dict):
            rows = [rows]

        positions: dict[str, Position] = {}
        for item in rows:
            if not isinstance(item, dict):
                raise BrokerRequestError("balance_position_row_invalid")
            symbol = str(item.get("ovrs_pdno") or item.get("pdno") or "").upper()
            if not symbol:
                raise BrokerRequestError("balance_position_symbol_invalid")
            qty = _position_quantity(item)
            if qty == 0:
                continue
            if symbol in positions:
                raise BrokerRequestError("balance_position_duplicate")
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
        self._balance_payload = self._read_balance_pages()
        return self._balance_payload

    def _read_balance_pages(self) -> JsonObject:
        rows: list[JsonObject] = []
        continuation_fk = ""
        continuation_nk = ""
        seen_continuations: set[tuple[str, str]] = set()
        previous_deadline = getattr(self, "_reconciliation_deadline", None)
        if previous_deadline is None:
            self._reconciliation_deadline = (
                self._retry_clock()
                + CANARY_POLICY.reconciliation_tick_deadline_seconds
            )
        try:
            for _page in range(CANARY_POLICY.maximum_reconciliation_pages):
                params = self._balance_params(continuation_fk, continuation_nk)
                if continuation_nk:
                    payload = self._request(
                        "GET",
                        "/uapi/overseas-stock/v1/trading/inquire-balance",
                        tr_id="VTTS3012R" if self.credentials.paper else "TTTS3012R",
                        params=params,
                        tr_cont="N",
                    )
                else:
                    payload = self._request(
                        "GET",
                        "/uapi/overseas-stock/v1/trading/inquire-balance",
                        tr_id="VTTS3012R" if self.credentials.paper else "TTTS3012R",
                        params=params,
                    )
                page_rows = payload.get("output1")
                if page_rows is None:
                    raise BrokerRequestError("balance_position_rows_missing")
                if isinstance(page_rows, dict):
                    page_rows = [page_rows]
                if not isinstance(page_rows, list) or any(
                    not isinstance(row, dict) for row in page_rows
                ):
                    raise BrokerRequestError("balance_position_rows_invalid")
                rows.extend(page_rows)
                next_keys = (
                    str(payload.get("ctx_area_fk200") or ""),
                    str(payload.get("ctx_area_nk200") or ""),
                )
                tr_cont = str(
                    payload.get("tr_cont") or getattr(self, "_last_tr_cont", "")
                )
                if tr_cont.upper() not in {"M", "F"}:
                    return {"output1": rows}
                if not next_keys[1] or next_keys in seen_continuations:
                    raise BrokerRequestError("balance_continuation_repeated")
                seen_continuations.add(next_keys)
                continuation_fk, continuation_nk = next_keys
        finally:
            self._reconciliation_deadline = previous_deadline
        raise BrokerRequestError("balance_continuation_page_limit")

    def _balance_params(
        self,
        continuation_fk: str,
        continuation_nk: str,
    ) -> dict[str, str]:
        return {
            "CANO": self.credentials.account_no,
            "ACNT_PRDT_CD": self.credentials.account_product_code,
            "OVRS_EXCG_CD": self.credentials.order_exchange_code,
            "TR_CRCY_CD": self.credentials.currency,
            "CTX_AREA_FK200": continuation_fk,
            "CTX_AREA_NK200": continuation_nk,
        }

    def _inquire_present_balance(self, refresh: bool = False) -> JsonObject:
        if self._present_balance_payload is not None and not refresh:
            return self._present_balance_payload
        self._present_balance_payload = self._request(
            "GET",
            "/uapi/overseas-stock/v1/trading/inquire-present-balance",
            tr_id="VTRP6504R" if self.credentials.paper else "CTRP6504R",
            params={
                "CANO": self.credentials.account_no,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "WCRC_FRCR_DVSN_CD": "02",
                "NATN_CD": "840",
                "TR_MKET_CD": "00",
                "INQR_DVSN_CD": "00",
            },
        )
        return self._present_balance_payload


def _position_quantity(row: JsonObject) -> float:
    for key in ("ovrs_cblc_qty", "cblc_qty", "qty"):
        if key not in row:
            continue
        value = row[key]
        if value is None or value == "" or isinstance(value, bool):
            break
        try:
            quantity = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            break
        if isfinite(quantity) and quantity >= 0:
            return quantity
        break
    raise BrokerRequestError("balance_position_quantity_invalid")
