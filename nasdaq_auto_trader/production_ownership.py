from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

from .ai_quant_lab.types import JsonValue
from .brokers.kis_reconciliation import KISOpenOrder, KISOrderHistory
from .file_lock import FileLockTimeout, exclusive_file_lock
from .market_hours import EASTERN
from .models import Position
from .session_claims import AcceptedBuyReceipt, ClaimStatus, SignalKey
from .trading_session_store import SessionStoreError, TradingSessionStore


class ProductionSessionStore(TradingSessionStore):
    def __init__(self, path: Path, account_digest: str) -> None:
        super().__init__(path)
        self.account_digest = account_digest
        self.managed_path = path.with_name("managed_buy_receipts.json")

    def complete(
        self, key: SignalKey, status: ClaimStatus,
        buy_receipt: AcceptedBuyReceipt | None = None,
    ) -> None:
        if buy_receipt is not None and buy_receipt.order_id:
            self._record_receipt(buy_receipt)
        super().complete(key, status, buy_receipt)

    def managed_receipts(self) -> tuple[AcceptedBuyReceipt, ...]:
        if not self.managed_path.exists():
            return ()
        try:
            payload: JsonValue = json.loads(self.managed_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SessionStoreError("production_managed_receipts_corrupt") from exc
        if not isinstance(payload, dict) or payload.get("account_digest") != self.account_digest:
            raise SessionStoreError("production_managed_receipts_binding_mismatch")
        rows = payload.get("receipts")
        if not isinstance(rows, list):
            raise SessionStoreError("production_managed_receipts_corrupt")
        receipts: list[AcceptedBuyReceipt] = []
        for row in rows:
            if not isinstance(row, dict):
                raise SessionStoreError("production_managed_receipts_corrupt")
            order_id, symbol, market_date = row.get("order_id"), row.get("symbol"), row.get("market_date")
            initial = row.get("initial_position_qty")
            planned = row.get("planned_quantity", 1.0)
            if (not isinstance(order_id, str) or not order_id or not isinstance(symbol, str)
                or not isinstance(market_date, str) or not isinstance(initial, int | float)
                or isinstance(initial, bool) or initial != 0
                or not isinstance(planned, int | float) or isinstance(planned, bool)
                or not math.isfinite(planned) or planned <= 0 or int(planned) != planned):
                raise SessionStoreError("production_managed_receipts_corrupt")
            receipts.append(AcceptedBuyReceipt(order_id, symbol, market_date, float(initial), float(planned)))
        return tuple(receipts)

    def _record_receipt(self, receipt: AcceptedBuyReceipt) -> None:
        if receipt.initial_position_qty != 0:
            raise SessionStoreError("production_existing_position_adoption_forbidden")
        self.managed_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with exclusive_file_lock(self.managed_path.with_suffix(".lock"), 2.0):
                previous = self.managed_receipts()
                receipts = {(item.market_date, item.order_id): item for item in previous}
                receipts[(receipt.market_date, receipt.order_id)] = receipt
                temporary = self.managed_path.with_suffix(".tmp")
                with temporary.open("w", encoding="utf-8") as output:
                    json.dump({"account_digest": self.account_digest,
                               "receipts": [asdict(item) for item in receipts.values()]}, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.managed_path)
        except OSError as exc:
            raise SessionStoreError("production_managed_receipts_write_failed") from exc
        except FileLockTimeout as exc:
            raise SessionStoreError("production_managed_receipts_lock_timeout") from exc


def owned_position(
    position: Position, receipts: Sequence[AcceptedBuyReceipt],
    history: Sequence[KISOrderHistory],
) -> bool:
    known = {(item.order_id, item.market_date) for item in receipts if item.symbol == position.symbol}
    known_ids = {order_id for order_id, _market_date in known}
    rows = [item for item in history if item.symbol == position.symbol and item.is_original_order]
    if not known or not rows or not math.isfinite(position.qty) or position.qty <= 0:
        return False
    net = 0.0
    for item in rows:
        if (not math.isfinite(item.filled_quantity) or not math.isfinite(item.quantity)
            or not 0 <= item.filled_quantity <= item.quantity):
            return False
        if item.side == "buy":
            if (item.submitted_at is None or item.submitted_at.tzinfo is None
                or item.submitted_at.utcoffset() is None):
                return False
            matching = next((receipt for receipt in receipts
                             if receipt.symbol == item.symbol
                             and receipt.order_id == item.order_id
                             and receipt.market_date == item.submitted_at.astimezone(EASTERN).date().isoformat()), None)
            if item.filled_quantity > 0 and (matching is None
                    or not math.isfinite(matching.planned_quantity)
                    or matching.planned_quantity <= 0
                    or int(matching.planned_quantity) != matching.planned_quantity
                    or item.quantity != matching.planned_quantity):
                return False
            net += item.filled_quantity
        elif item.side == "sell":
            net -= item.filled_quantity
        else:
            return False
    average_matches = any(
        item.side == "buy" and item.order_id in known_ids and item.filled_quantity > 0
        and math.isfinite(item.average_fill_price) and item.average_fill_price > 0
        and math.isclose(item.average_fill_price, position.avg_entry_price, rel_tol=1e-6)
        for item in rows
    )
    return average_matches and math.isclose(net, position.qty, rel_tol=1e-8, abs_tol=1e-8)


def foreign_portfolio_counts(
    positions: Mapping[str, Position], pending: Sequence[KISOpenOrder],
    ownership: tuple[Sequence[AcceptedBuyReceipt], Sequence[KISOrderHistory]],
) -> tuple[int, int]:
    receipts, history = ownership
    keys = {(item.order_id, item.symbol, item.market_date) for item in receipts}
    foreign_held = sum(not owned_position(position, receipts, history) for position in positions.values())
    foreign_pending = sum(not (
        any(row.order_id == item.order_id and row.symbol == item.symbol and row.side == "buy"
            and row.is_original_order and row.submitted_at is not None
            and row.submitted_at.tzinfo is not None and row.submitted_at.utcoffset() is not None
            and (item.order_id, item.symbol, row.submitted_at.astimezone(EASTERN).date().isoformat()) in keys
            and any(receipt.order_id == item.order_id and receipt.symbol == item.symbol
                    and receipt.market_date == row.submitted_at.astimezone(EASTERN).date().isoformat()
                    and item.quantity == row.quantity == receipt.planned_quantity
                    for receipt in receipts)
            for row in history) and item.side == "buy"
        and math.isfinite(item.quantity) and item.quantity > 0
        and int(item.quantity) == item.quantity
        and 0 <= item.filled_quantity <= item.quantity
    ) for item in pending)
    return foreign_held, foreign_pending
