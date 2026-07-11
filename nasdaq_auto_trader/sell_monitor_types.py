from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from .models import AccountSnapshot, OrderRequest, Position


HIVE_SYMBOL = "HIVE"
JsonObject = dict[str, Any]
SellMonitorResult = dict[str, Any]


class SellMonitorConfigError(ValueError):
    pass


class SellMonitorSafetyError(RuntimeError):
    pass


class SellMonitorClient(Protocol):
    """Client methods used by the HIVE sell-only monitor."""

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        """Return account values."""

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        """Return current positions keyed by symbol."""

    def get_price_detail(self, symbol: str) -> JsonObject:
        """Return current price detail fields."""

    def get_best_quote(self, symbol: str) -> JsonObject:
        """Return current best bid and ask."""

    def submit_order(self, order: OrderRequest) -> JsonObject:
        """Submit a broker order."""


@dataclass(frozen=True, slots=True)
class HiveSellMonitorConfig:
    """Sell-only settings for managing the existing HIVE position."""

    symbol: str = HIVE_SYMBOL
    qty: int = 1
    sell_only: bool = True
    take_profit_pct: float = 1.5
    stop_loss_enabled: bool = False
    stop_loss_pct: float = -1.0
    trailing_stop_enabled: bool = False
    trailing_stop_pct: float = 0.8
    force_sell_before_close_enabled: bool = False
    max_hold_until_market_close: bool = False
    force_sell_before_close_minutes: int = 10
    allow_additional_buy: bool = False
    sell_only_when_profit: bool = True
    hold_if_unprofitable: bool = True
    require_confirm_before_loss_sell: bool = True
    max_retries: int = 3
    poll_seconds: float = 30.0
    fill_check_seconds: float = 90.0
    fill_poll_seconds: float = 10.0
    marketable_limit_buffer_pct: float = 0.2
    dry_run: bool = False
    record_path: Path = Path("logs/hive_sell_monitor.jsonl")


@dataclass(frozen=True, slots=True)
class SellSnapshot:
    """One refreshed view of the HIVE position and quote."""

    session: JsonObject
    account: AccountSnapshot
    position: Position | None
    current_price: float
    bid: float
    ask: float
    avg_entry_price: float
    qty: float
    take_profit_price: float
    stop_loss_price: float
    trailing_stop_price: float | None
    force_sell_at: str
    pnl_pct: float

    def to_dict(self) -> JsonObject:
        data = asdict(self)
        data["account"] = {
            "cash": round(self.account.cash, 4),
            "equity": round(self.account.equity, 4),
            "buying_power": round(self.account.buying_power, 4),
        }
        if self.position is not None:
            data["position"] = {
                "symbol": self.position.symbol,
                "qty": self.position.qty,
                "market_value": round(self.position.market_value, 4),
                "avg_entry_price": round(self.position.avg_entry_price, 4),
            }
        for key, value in list(data.items()):
            if isinstance(value, float):
                data[key] = round(value, 6)
        return data
