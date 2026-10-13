from __future__ import annotations

from math import isfinite

from .backtest_costs import BacktestCosts
from .models import Bar, OrderRequest


class ConservativeCosts(BacktestCosts):
    """An admissible next open is a simulation assumption, not a guaranteed fill."""

    def fill_price(self, order: OrderRequest, bar: Bar) -> tuple[float, float] | None:
        if order.side == "buy" and order.type == "limit":
            if order.limit_price is None or not isfinite(bar.volume) or bar.volume <= 0:
                return None
            price = bar.open * (1 + self.adverse_fraction)
            if price > order.limit_price:
                return None
            return price, price - bar.open
        return super().fill_price(order, bar)
