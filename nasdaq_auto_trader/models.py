"""Shared data structures for market data, decisions, and orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict


Action = Literal["buy", "sell", "hold"]
OrderSide = Literal["buy", "sell"]


class AlpacaOrderPayload(TypedDict, total=False):
    symbol: str
    side: OrderSide
    type: str
    time_in_force: str
    qty: str
    notional: str
    limit_price: str


@dataclass(frozen=True, slots=True)
class OrderRequestPayloadError(ValueError):
    symbol: str
    reason: str

    def __str__(self) -> str:
        return f"invalid order payload for {self.symbol}: {self.reason}"


@dataclass(frozen=True, slots=True)
class Bar:
    """OHLCV market data for one symbol at one timestamp."""

    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_alpaca(cls, symbol: str, payload: dict) -> "Bar":
        """Build a Bar from Alpaca's compact stock-bar payload."""

        return cls(
            symbol=symbol,
            timestamp=str(payload["t"]),
            open=float(payload["o"]),
            high=float(payload["h"]),
            low=float(payload["l"]),
            close=float(payload["c"]),
            volume=float(payload.get("v", 0)),
        )


@dataclass(frozen=True, slots=True)
class Position:
    """Current holding state for one symbol."""

    symbol: str
    qty: float
    market_value: float
    avg_entry_price: float


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """Capital values needed before building an order."""

    cash: float
    equity: float
    buying_power: float


@dataclass(frozen=True, slots=True)
class TradeDecision:
    """A strategy decision and optional risk distance for position sizing."""

    symbol: str
    action: Action
    score: int
    latest_price: float
    reasons: list[str] = field(default_factory=list)
    risk_per_share: float | None = None


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """A broker-neutral order request shaped for Alpaca serialization."""

    symbol: str
    side: OrderSide
    type: str = "market"
    time_in_force: str = "day"
    qty: float | None = None
    notional: float | None = None
    limit_price: float | None = None

    def to_alpaca_payload(self) -> AlpacaOrderPayload:
        """Return the JSON body accepted by Alpaca's order endpoint."""

        if self.qty is not None and self.notional is not None:
            raise OrderRequestPayloadError(
                self.symbol,
                "qty and notional are mutually exclusive",
            )
        payload: AlpacaOrderPayload = {
            "symbol": self.symbol,
            "side": self.side,
            "type": self.type,
            "time_in_force": self.time_in_force,
        }
        if self.qty is not None:
            payload["qty"] = str(round(self.qty, 8))
        if self.notional is not None:
            payload["notional"] = str(round(self.notional, 2))
        if self.limit_price is not None:
            payload["limit_price"] = str(round(self.limit_price, 4))
        return payload
