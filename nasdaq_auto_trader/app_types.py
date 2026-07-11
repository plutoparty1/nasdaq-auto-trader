from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .models import AccountSnapshot


AutoTradeState = Literal["stopped", "running", "paused"]
EngineResult = dict[str, Any]


class AppConfigurationError(ValueError):
    pass


class GuiUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PositionRow:
    """Display-ready position data."""

    symbol: str
    qty: float
    avg_entry_price: float
    market_value: float
    latest_price: float | None
    unrealized_pl: float | None
    unrealized_pl_pct: float | None


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Display-ready account and holdings snapshot."""

    as_of: datetime
    mode: str
    broker: str
    account: AccountSnapshot
    positions: list[PositionRow]
