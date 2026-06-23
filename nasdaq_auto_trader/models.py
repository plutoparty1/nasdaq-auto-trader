"""자동매매 흐름에서 같이 쓰는 작은 데이터 모양들을 정의한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Action = Literal["buy", "sell", "hold"]
OrderSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class Bar:
    """한 시점의 가격 봉 데이터를 담는다."""

    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_alpaca(cls, symbol: str, payload: dict) -> "Bar":
        """Alpaca 응답의 짧은 키 이름을 내부 Bar 모양으로 바꾼다."""

        return cls(
            symbol=symbol,
            timestamp=str(payload["t"]),
            open=float(payload["o"]),
            high=float(payload["h"]),
            low=float(payload["l"]),
            close=float(payload["c"]),
            volume=float(payload.get("v", 0)),
        )


@dataclass(frozen=True)
class Position:
    """현재 들고 있는 종목 수량과 평균 매수가를 담는다."""

    symbol: str
    qty: float
    market_value: float
    avg_entry_price: float


@dataclass(frozen=True)
class AccountSnapshot:
    """주문 전에 필요한 현금과 계좌 크기를 담는다."""

    cash: float
    equity: float
    buying_power: float


@dataclass(frozen=True)
class TradeDecision:
    """전략이 낸 매수, 매도, 대기 판단을 담는다."""

    symbol: str
    action: Action
    score: int
    latest_price: float
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OrderRequest:
    """브로커에게 보낼 주문 내용을 담는다."""

    symbol: str
    side: OrderSide
    type: str = "market"
    time_in_force: str = "day"
    qty: float | None = None
    notional: float | None = None

    def to_alpaca_payload(self) -> dict:
        """Alpaca 주문 API가 받는 JSON 모양으로 바꾼다."""

        payload = {
            "symbol": self.symbol,
            "side": self.side,
            "type": self.type,
            "time_in_force": self.time_in_force,
        }
        if self.qty is not None:
            payload["qty"] = str(round(self.qty, 8))
        if self.notional is not None:
            payload["notional"] = str(round(self.notional, 2))
        return payload
