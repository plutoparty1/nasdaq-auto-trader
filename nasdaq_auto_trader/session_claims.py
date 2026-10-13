from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum, unique


@unique
class ClaimStatus(StrEnum):
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class SignalKey:
    market_date: str
    strategy_id: str
    strategy_version: str
    symbol: str
    side: str
    signal_timestamp: str

    def digest(self) -> str:
        canonical = "|".join(
            (
                self.market_date,
                self.strategy_id,
                self.strategy_version,
                self.symbol,
                self.side,
                self.signal_timestamp,
            )
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ClaimDecision:
    granted: bool
    reason: str
    status: ClaimStatus


@dataclass(frozen=True, slots=True)
class AcceptedBuyReceipt:
    order_id: str
    symbol: str
    market_date: str
    initial_position_qty: float
    planned_quantity: float = 1.0


@dataclass(frozen=True, slots=True)
class ClaimRecord:
    status: ClaimStatus
    market_date: str
    buy_receipt: AcceptedBuyReceipt | None = None
