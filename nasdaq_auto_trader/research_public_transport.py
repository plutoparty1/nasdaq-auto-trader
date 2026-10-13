"""Public GET-only research transport, independent of application credentials."""

from __future__ import annotations

import re
import ssl
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as day_time
from http.client import HTTPSConnection
from typing import Final
from urllib.parse import parse_qs, urlsplit

import certifi

SYMBOLS = ("CMCSA", "KDP", "HIVE", "SPY")
P1_SYMBOLS: Final = ("CMCSA", "HIVE", "KDP")


class PublicDataError(RuntimeError):
    """Sanitized public research failure code."""


@dataclass(frozen=True, slots=True)
class PublicRequestBounds:
    start: date
    end: date
    now: datetime

    def __post_init__(self) -> None:
        if (
            self.now.utcoffset() is None
            or not self.start <= self.end <= self.now.astimezone(UTC).date()
            or (self.end - self.start).days > 366
        ):
            raise PublicDataError("public_bounds_invalid")


def validate_public_request(
    method: str, url: str, *, bounds: PublicRequestBounds | None = None
) -> None:
    parts = urlsplit(url)
    if (
        method != "GET"
        or parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port
        or parts.fragment
    ):
        raise PublicDataError("public_endpoint_denied")
    query = parse_qs(parts.query, keep_blank_values=True)
    if any(len(values) != 1 for values in query.values()):
        raise PublicDataError("public_query_denied")
    flat = {key: values[0] for key, values in query.items()}
    if parts.netloc == "query1.finance.yahoo.com" and parts.path in {
        f"/v8/finance/chart/{symbol}"
        for symbol in (P1_SYMBOLS if bounds is not None else SYMBOLS)
    }:
        if set(flat) != {
            "period1",
            "period2",
            "interval",
            "events",
            "includeAdjustedClose",
        }:
            raise PublicDataError("public_query_denied")
        if (
            flat["interval"] != "1d"
            or flat["events"] != "div,splits"
            or flat["includeAdjustedClose"] != "true"
        ):
            raise PublicDataError("public_query_denied")
        if not all(
            re.fullmatch(r"[0-9]{10}", flat[key]) for key in ("period1", "period2")
        ):
            raise PublicDataError("public_period_denied")
        lower, upper = 1724976000, 1790640000
        if bounds is not None:
            if int(flat["period2"]) - int(flat["period1"]) > 366 * 86400:
                raise PublicDataError("public_period_denied")
            lower = int(datetime.combine(bounds.start, day_time(), UTC).timestamp())
            upper = int(
                min(
                    datetime.combine(bounds.end + timedelta(days=1), day_time(), UTC),
                    bounds.now,
                ).timestamp()
            )
        if not lower <= int(flat["period1"]) < int(flat["period2"]) <= upper:
            raise PublicDataError("public_period_denied")
        return
    if (
        parts.netloc == "data-api.ecb.europa.eu"
        and parts.path == "/service/data/EXR/D.USD+KRW.EUR.SP00.A"
    ):
        if bounds is None:
            if flat == {
                "startPeriod": "2024-08-30",
                "endPeriod": "2026-09-28",
                "format": "csvdata",
            }:
                return
        elif (
            set(flat) == {"startPeriod", "endPeriod", "format"}
            and flat["format"] == "csvdata"
        ):
            try:
                start, end = (
                    date.fromisoformat(flat["startPeriod"]),
                    date.fromisoformat(flat["endPeriod"]),
                )
            except ValueError:
                raise PublicDataError("public_period_denied") from None
            if bounds.start <= start <= end <= bounds.end:
                return
    raise PublicDataError("public_endpoint_denied")


def public_get(url: str, *, bounds: PublicRequestBounds | None = None) -> bytes:
    validate_public_request("GET", url, bounds=bounds)
    parts = urlsplit(url)
    for attempt in range(2):
        try:
            with closing(
                HTTPSConnection(
                    parts.netloc,
                    timeout=20,
                    context=ssl.create_default_context(cafile=certifi.where()),
                )
            ) as connection:
                connection.request(
                    "GET",
                    parts.path + "?" + parts.query,
                    headers={
                        "User-Agent": "NasdaqAutoTrader-OfflineResearch/1.0",
                        "Accept": "application/json,text/csv",
                    },
                )
                response = connection.getresponse()
                if 300 <= response.status < 400:
                    raise PublicDataError("public_redirect_denied")
                if response.status == 429 and attempt == 0:
                    time.sleep(2)
                    continue
                if response.status != 200:
                    raise PublicDataError(f"public_http_{response.status}")
                content = response.read(8_000_001)
                if len(content) > 8_000_000:
                    raise PublicDataError("public_response_too_large")
                return content
        except (OSError, TimeoutError):
            if attempt == 1:
                raise PublicDataError("public_transport_unavailable") from None
            time.sleep(2)
    raise PublicDataError("public_retry_limit")
