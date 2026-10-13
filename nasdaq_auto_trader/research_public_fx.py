from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import date
from typing import Final

from .research_public_transport import PublicDataError

DEFAULT_START: Final = date(2024, 8, 30)
DEFAULT_END: Final = date(2026, 9, 28)


@dataclass(frozen=True, slots=True)
class PublicFx:
    timestamp: str
    usdkrw: float


def parse_ecb_fx(
    content: bytes,
    *,
    start: date = DEFAULT_START,
    end: date = DEFAULT_END,
) -> tuple[PublicFx, ...]:
    try:
        days: dict[str, dict[str, float]] = {}
        for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
            currency, day = row["CURRENCY"], row["TIME_PERIOD"]
            value = float(row["OBS_VALUE"])
            if (
                currency not in {"USD", "KRW"}
                or not math.isfinite(value)
                or value <= 0
                or not start <= date.fromisoformat(day) <= end
            ):
                raise PublicDataError("public_fx_invalid")
            rates = days.setdefault(day, {})
            if currency in rates:
                raise PublicDataError("public_fx_duplicate")
            rates[currency] = value
        if not days or any(set(rates) != {"USD", "KRW"} for rates in days.values()):
            raise PublicDataError("public_fx_cross_missing")
        return tuple(
            PublicFx(day + "T16:00:00+00:00", rates["KRW"] / rates["USD"])
            for day, rates in sorted(days.items())
        )
    except (ValueError, TypeError, KeyError, UnicodeError, csv.Error):
        raise PublicDataError("public_fx_payload_invalid") from None
