"""Paper-only KIS transport boundary for a single persisted P1 submission window."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps
from math import isfinite
from pathlib import Path
from typing import final, override
from urllib.parse import urlsplit
from urllib.request import Request

from .brokers.common import BrokerRequestError
from .brokers.kis_client import KISClient, KISCredentials
from .brokers.kis_pricing import normalize_kis_limit_price
from .entry_comparison import JsonValue
from .live_canary_lease import BrokerLeaseError
from .models import OrderRequest
from .p1_paper_codec import read_json
from .p1_paper_protocol import mapping


@final
class P1SubmissionBlocked(BrokerRequestError):
    """A known pre-transport refusal; no order POST has been sent."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class SubmissionWindow:
    order: OrderRequest
    open_at: datetime
    deadline: datetime


@final
class P1OperatingKISClient(KISClient):
    def __init__(self, credentials: KISCredentials, token_cache_path: str | Path | None = None,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        if not credentials.paper:
            raise P1SubmissionBlocked('paper_mode_required')
        super().__init__(credentials, token_cache_path)
        self._submission_clock = clock
        self._submission_window: SubmissionWindow | None = None
        self._submission_active = False

    def bind_submission_window(self, order: OrderRequest, open_at: datetime, deadline: datetime) -> None:
        if self._submission_active:
            raise P1SubmissionBlocked('submission_already_active')
        if (open_at.tzinfo is None or deadline.tzinfo is None or deadline <= open_at
                or order.type != 'limit' or order.time_in_force != 'day'
                or order.qty is None or not isfinite(order.qty) or order.qty <= 0
                or not float(order.qty).is_integer() or order.notional is not None
                or order.limit_price is None or not isfinite(order.limit_price) or order.limit_price <= 0):
            raise P1SubmissionBlocked('submission_window_invalid')
        self._submission_window = SubmissionWindow(order, open_at, deadline)

    def _assert_lease(self, order: OrderRequest) -> None:
        if self._broker_live_lease is None:
            raise P1SubmissionBlocked('submission_lease_required')
        try:
            self._broker_live_lease.assert_allowed(self._broker_lease_path, self.account_fingerprint, order.side)
        except BrokerLeaseError as error:
            raise P1SubmissionBlocked('submission_lease_invalid') from error

    @override
    def submit_order(self, order: OrderRequest) -> dict[str, JsonValue]:
        window = self._submission_window
        if window is None:
            raise P1SubmissionBlocked('submission_window_missing')
        try:
            if self._submission_active or window.order != order:
                raise P1SubmissionBlocked('submission_order_mismatch')
            self._assert_lease(order)
            self._submission_active = True
            return mapping(read_json(dumps(super().submit_order(order), allow_nan=False)))
        finally:
            self._submission_window = None
            self._submission_active = False

    def _assert_order_request(self, request: Request) -> None:
        window = self._submission_window
        if window is None or not self._submission_active:
            raise P1SubmissionBlocked('submission_window_missing')
        order = window.order
        self._assert_lease(order)
        if not isinstance(request.data, bytes) or order.limit_price is None or order.qty is None:
            raise P1SubmissionBlocked('submission_payload_invalid')
        body = mapping(read_json(request.data.decode('utf-8')))
        expected = {'CANO': self.credentials.account_no, 'ACNT_PRDT_CD': self.credentials.account_product_code,
                    'OVRS_EXCG_CD': self.credentials.order_exchange_code, 'PDNO': order.symbol,
                    'ORD_QTY': str(int(order.qty)), 'ORD_DVSN': '00',
                    'OVRS_ORD_UNPR': str(normalize_kis_limit_price(Decimal(str(order.limit_price)), order.side))}
        if (any(body.get(key) != value for key, value in expected.items())
                or request.get_header('Tr_id') != self._order_tr_id(order.side)):
            raise P1SubmissionBlocked('submission_order_mismatch')
        now = self._submission_clock()
        if now.tzinfo is None or now < window.open_at or now >= window.deadline:
            raise P1SubmissionBlocked('submission_window_elapsed')
        self._submission_window = None

    @override
    def _open_json(self, request: Request, label: str) -> dict[str, JsonValue]:
        target, paper = urlsplit(request.full_url), urlsplit(self.paper_base_url)
        if not self.credentials.paper:
            raise P1SubmissionBlocked('paper_mode_required')
        if (target.scheme, target.netloc) != (paper.scheme, paper.netloc) or self.base_url != self.paper_base_url:
            raise P1SubmissionBlocked('paper_host_required')
        if request.get_method() == 'POST' and target.path == '/uapi/overseas-stock/v1/trading/order':
            self._assert_order_request(request)
        elif request.get_method() != 'GET' and not (
                request.get_method() == 'POST' and target.path == '/oauth2/tokenP'):
            raise P1SubmissionBlocked('submission_mutation_forbidden')
        return mapping(read_json(dumps(super()._open_json(request, label), allow_nan=False)))
