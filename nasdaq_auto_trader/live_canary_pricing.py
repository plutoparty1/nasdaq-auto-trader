from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .brokers.kis_pricing import normalize_kis_limit_price


MarketField = str | int | float | None


@dataclass(frozen=True, slots=True)
class CanaryExitPriceError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def marketable_exit_price(
    quote: Mapping[str, MarketField],
    previous_limit: Decimal | None,
) -> Decimal:
    bid = _positive_decimal(quote, "pbid1", "bid")
    step = Decimal("0.01") if bid >= 1 else Decimal("0.0001")
    price = bid if previous_limit is None else min(bid, previous_limit - step)
    normalized = normalize_kis_limit_price(price, "sell")
    if normalized <= 0:
        raise CanaryExitPriceError("marketable exit price is not positive")
    return normalized


def _positive_decimal(
    quote: Mapping[str, MarketField],
    *keys: str,
) -> Decimal:
    for key in keys:
        value = quote.get(key)
        if value in (None, "") or isinstance(value, bool):
            continue
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            continue
        if parsed.is_finite() and parsed > 0:
            return parsed
    raise CanaryExitPriceError("best bid is missing or invalid")
