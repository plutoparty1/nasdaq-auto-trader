from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from ..live_canary_lease import broker_submission_guard
from ..live_canary_policy import CANARY_POLICY
from ..models import OrderSide
from .common import BrokerRequestError, JsonObject, _first_float, _format_price
from .kis_history import history_status, history_submitted_at, is_original_order


@dataclass(frozen=True, slots=True)
class KISOpenOrder:

    order_id: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    limit_price: float


@dataclass(frozen=True, slots=True)
class KISOrderHistory:

    order_id: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float
    average_fill_price: float
    status: str = "unknown"
    submitted_at: datetime | None = None
    is_original_order: bool = True


@dataclass(frozen=True, slots=True)
class KISCancelOrder:

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    limit_price: float


@dataclass(frozen=True, slots=True)
class KISCancelResult:

    order_id: str
    cancellation_order_id: str = ""


class KISReconciliationMixin:
    @contextmanager
    def reconciliation_window(self, deadline_seconds: float) -> Iterator[None]:
        previous_deadline = getattr(self, "_reconciliation_deadline", None)
        self._reconciliation_deadline = self._retry_clock() + deadline_seconds
        try:
            yield
        finally:
            self._reconciliation_deadline = previous_deadline

    def list_open_orders(self) -> tuple[KISOpenOrder, ...]:
        rows = self._read_pages(
            "/uapi/overseas-stock/v1/trading/inquire-nccs",
            "VTTS3018R" if self.credentials.paper else "TTTS3018R",
            {
                "CANO": self.credentials.account_no,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "OVRS_EXCG_CD": self.credentials.order_exchange_code,
                "SORT_SQN": "DS",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
        return tuple(self._parse_open_order(row) for row in rows)

    def list_order_history(self, start_date: str, end_date: str) -> tuple[KISOrderHistory, ...]:
        rows = self._read_pages(
            "/uapi/overseas-stock/v1/trading/inquire-ccnl",
            "VTTS3035R" if self.credentials.paper else "TTTS3035R",
            {
                "CANO": self.credentials.account_no,
                "ACNT_PRDT_CD": self.credentials.account_product_code,
                "PDNO": "" if self.credentials.paper else "%",
                "ORD_STRT_DT": start_date,
                "ORD_END_DT": end_date,
                "SLL_BUY_DVSN": "00",
                "CCLD_NCCS_DVSN": "00",
                "OVRS_EXCG_CD": "" if self.credentials.paper else self.credentials.order_exchange_code,
                "SORT_SQN": "DS",
                "ORD_DT": "",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
        return tuple(self._parse_history(row, rows) for row in rows)

    def cancel_order(self, order: KISCancelOrder) -> KISCancelResult:
        if not order.order_id or not order.symbol or order.quantity <= 0:
            raise BrokerRequestError("cancel_order_identity_invalid")
        if order.side not in ("buy", "sell"):
            raise BrokerRequestError("cancel_order_side_invalid")
        with broker_submission_guard(
            self._broker_lease_path,
            self.account_fingerprint,
            order.side,
            self._broker_live_lease,
        ):
            payload = self._request(
                "POST",
                "/uapi/overseas-stock/v1/trading/order-rvsecncl",
                tr_id="VTTT1004U" if self.credentials.paper else "TTTT1004U",
                body={
                    "CANO": self.credentials.account_no,
                    "ACNT_PRDT_CD": self.credentials.account_product_code,
                    "OVRS_EXCG_CD": self.credentials.order_exchange_code,
                    "PDNO": order.symbol,
                    "ORGN_ODNO": order.order_id,
                    "RVSE_CNCL_DVSN_CD": "02",
                    "ORD_QTY": _format_price(order.quantity),
                    "OVRS_ORD_UNPR": "0",
                    "MGCO_APTM_ODNO": "",
                    "ORD_SVR_DVSN_CD": "0",
                },
            )
        output = payload.get("output")
        confirmed_id = (
            str(output.get("ODNO") or "")
            if isinstance(output, dict)
            else ""
        )
        if not confirmed_id:
            raise BrokerRequestError("cancel_order_number_missing")
        return KISCancelResult(
            order_id=order.order_id,
            cancellation_order_id=confirmed_id,
        )

    def _read_pages(self, path: str, tr_id: str, params: dict[str, str]) -> list[JsonObject]:
        previous_deadline = getattr(self, "_reconciliation_deadline", None)
        if previous_deadline is None:
            self._reconciliation_deadline = (
                self._retry_clock()
                + CANARY_POLICY.reconciliation_tick_deadline_seconds
            )
        try:
            return self._read_pages_bounded(path, tr_id, params)
        finally:
            self._reconciliation_deadline = previous_deadline

    def _read_pages_bounded(self, path: str, tr_id: str, params: dict[str, str]) -> list[JsonObject]:
        rows: list[JsonObject] = []
        continuation_fk = ""
        continuation_nk = ""
        seen_continuations: set[tuple[str, str]] = set()
        for _page in range(CANARY_POLICY.maximum_reconciliation_pages):
            request_params = dict(params)
            request_params["CTX_AREA_FK200"] = continuation_fk
            request_params["CTX_AREA_NK200"] = continuation_nk
            payload = self._request(
                "GET",
                path,
                tr_id=tr_id,
                params=request_params,
                tr_cont="N" if continuation_nk else "",
            )
            if "output" in payload:
                raw_rows = payload["output"]
            elif "output1" in payload:
                raw_rows = payload["output1"]
            else:
                raise BrokerRequestError("kis_reconciliation_rows_missing")
            if isinstance(raw_rows, dict):
                raw_rows = [raw_rows]
            if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
                raise BrokerRequestError("kis_reconciliation_rows_invalid")
            rows.extend(raw_rows)
            next_fk = str(payload.get("ctx_area_fk200") or "")
            next_nk = str(payload.get("ctx_area_nk200") or "")
            tr_cont = str(payload.get("tr_cont") or getattr(self, "_last_tr_cont", ""))
            if tr_cont.upper() not in {"M", "F"}:
                return rows
            next_keys = (next_fk, next_nk)
            if not next_nk or next_keys in seen_continuations:
                raise BrokerRequestError("continuation_repeated")
            seen_continuations.add(next_keys)
            continuation_fk, continuation_nk = next_keys
        raise BrokerRequestError("continuation_page_limit")

    def _parse_open_order(self, row: JsonObject) -> KISOpenOrder:
        order_id = str(row.get("odno") or "")
        symbol = str(row.get("pdno") or "").upper()
        side_code = str(row.get("sll_buy_dvsn_cd") or "")
        quantity = _first_float(row, "ft_ord_qty", "ord_qty", default=-1.0)
        filled = _first_float(row, "ft_ccld_qty", "ccld_qty", default=-1.0)
        price = _first_float(row, "ft_ord_unpr3", "ft_ord_unpr", "ord_unpr", default=-1.0)
        if side_code not in {"01", "02"} or not order_id or not symbol or quantity < 0 or filled < 0 or price < 0:
            raise BrokerRequestError("open_order_row_invalid")
        remaining = quantity - filled
        if not isfinite(remaining) or remaining < 0:
            raise BrokerRequestError("open_order_row_invalid")
        side = "sell" if side_code == "01" else "buy"
        return KISOpenOrder(order_id, symbol, side, quantity, filled, remaining, price)

    def _parse_history(self, row: JsonObject, rows: list[JsonObject]) -> KISOrderHistory:
        order_id = str(row.get("odno") or "")
        symbol = str(row.get("pdno") or "").upper()
        side_code = str(row.get("sll_buy_dvsn_cd") or "")
        quantity = _first_float(row, "ft_ord_qty", "ord_qty", default=-1.0)
        filled = _first_float(row, "ft_ccld_qty", "ccld_qty", default=-1.0)
        price = _first_float(row, "ft_ccld_unpr", "ft_ccld_unpr3", default=-1.0)
        if side_code not in {"01", "02"} or not order_id or not symbol or quantity < 0 or filled < 0 or price < 0:
            raise BrokerRequestError("order_history_row_invalid")
        side = "sell" if side_code == "01" else "buy"
        return KISOrderHistory(
            order_id, symbol, side, quantity, filled, price,
            status=history_status(row, rows, quantity, filled),
            submitted_at=history_submitted_at(row),
            is_original_order=is_original_order(row),
        )
