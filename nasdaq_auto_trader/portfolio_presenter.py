from __future__ import annotations

from .app_types import PositionRow
from .models import Position


def position_to_row(position: Position) -> PositionRow:
    latest_price = None
    if position.qty > 0 and position.market_value > 0:
        latest_price = position.market_value / position.qty

    basis = position.avg_entry_price * position.qty
    unrealized_pl = None
    unrealized_pl_pct = None
    if basis > 0 and position.market_value > 0:
        unrealized_pl = position.market_value - basis
        unrealized_pl_pct = (unrealized_pl / basis) * 100

    return PositionRow(
        symbol=position.symbol,
        qty=round(position.qty, 8),
        avg_entry_price=round(position.avg_entry_price, 4),
        market_value=round(position.market_value, 4),
        latest_price=_round_optional(latest_price, 4),
        unrealized_pl=_round_optional(unrealized_pl, 4),
        unrealized_pl_pct=_round_optional(unrealized_pl_pct, 4),
    )


def _round_optional(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)
