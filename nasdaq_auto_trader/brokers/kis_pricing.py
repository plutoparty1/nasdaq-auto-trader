from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Final, assert_never

from ..models import OrderSide


ONE_DOLLAR: Final = Decimal("1")
CENT_TICK: Final = Decimal("0.01")
SUB_DOLLAR_TICK: Final = Decimal("0.0001")


def normalize_kis_limit_price(price: Decimal, side: OrderSide) -> Decimal:
    tick = CENT_TICK if price >= ONE_DOLLAR else SUB_DOLLAR_TICK
    match side:
        case "buy":
            rounding = ROUND_CEILING
        case "sell":
            rounding = ROUND_FLOOR
        case unreachable:
            assert_never(unreachable)
    normalized = price.quantize(tick, rounding=rounding)
    if normalized >= ONE_DOLLAR:
        return normalized.quantize(CENT_TICK, rounding=rounding)
    return normalized
