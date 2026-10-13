from __future__ import annotations

import csv
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .research_readonly import (
    DAILY,
    HISTORY,
    SYMBOLS,
    JsonMap,
    JsonValue,
    Query,
    ReadOnlyKIS,
    ResearchError,
)
from .research_readonly_contract import rows_of
from .research_readonly_history import summarize_history
from .research_readonly_minute import minute

__all__ = ["daily", "history", "minute", "rows_of"]


def history(client: ReadOnlyKIS, private: Path) -> JsonMap:
    all_rows: list[JsonMap] = []
    windows = (
        ("20260401", "20260430"),
        ("20260501", "20260531"),
        ("20260601", "20260630"),
        ("20260701", "20260731"),
        ("20260801", "20260831"),
        ("20260901", "20260928"),
    )
    outcomes: list[JsonValue] = []
    for start, end in windows:
        params = {
            "CANO": client.credentials.account,
            "ACNT_PRDT_CD": client.credentials.product,
            "PDNO": "%",
            "ORD_STRT_DT": start,
            "ORD_END_DT": end,
            "SLL_BUY_DVSN": "00",
            "CCLD_NCCS_DVSN": "00",
            "OVRS_EXCG_CD": "NASD",
            "SORT_SQN": "DS",
            "ORD_DT": "",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        seen: set[tuple[str, str]] = set()
        count = 0
        status = "page_limit"
        try:
            for page in range(10):
                payload, continuation = client.get(
                    Query(HISTORY, "TTTS3035R", params, "N" if page else "")
                )
                rows = rows_of(payload, "output")
                all_rows.extend(rows)
                count += len(rows)
                if continuation not in {"M", "F"}:
                    status = "complete"
                    break
                cursor = (
                    str(payload.get("ctx_area_fk200") or ""),
                    str(payload.get("ctx_area_nk200") or ""),
                )
                if not cursor[1] or cursor in seen:
                    raise ResearchError("history_cursor_repeated")
                seen.add(cursor)
                params["CTX_AREA_FK200"], params["CTX_AREA_NK200"] = cursor
        except ResearchError as exc:
            status = str(exc)
        outcomes.append({"start": start, "end": end, "rows": count, "status": status})
    (private / "history-private.json").write_text(
        json.dumps(all_rows, ensure_ascii=False), encoding="utf-8"
    )
    result = summarize_history(all_rows)
    result["windows"] = outcomes
    return result


def daily(client: ReadOnlyKIS, private: Path, symbol: str) -> JsonMap:
    start, cursor = "20240928", "20260928"
    collected: dict[str, JsonMap] = {}
    duplicates = 0
    status = "page_limit"
    raw_pages: list[JsonValue] = []
    try:
        for _page in range(20):
            payload, _ = client.get(
                Query(
                    DAILY,
                    "HHDFS76240000",
                    {
                        "AUTH": "",
                        "EXCD": SYMBOLS[symbol],
                        "SYMB": symbol,
                        "GUBN": "0",
                        "BYMD": cursor,
                        "MODP": "1",
                    },
                )
            )
            raw_pages.append(payload)
            rows = rows_of(payload, "output2")
            if not rows:
                status = "no_more_rows"
                break
            dates = [str(row.get("xymd") or "") for row in rows]
            if any(len(day) != 8 or not day.isdigit() for day in dates):
                raise ResearchError("daily_date_invalid")
            for day, row in zip(dates, rows):
                if day in collected:
                    duplicates += 1
                    if collected[day] != row:
                        raise ResearchError("daily_duplicate_conflict")
                if start <= day <= "20260928":
                    collected[day] = row
            oldest = min(dates)
            if oldest <= start:
                status = "requested_start_reached"
                break
            next_cursor = (date.fromisoformat(oldest) - timedelta(days=1)).strftime(
                "%Y%m%d"
            )
            if next_cursor >= cursor:
                raise ResearchError("daily_cursor_not_advancing")
            cursor = next_cursor
    except ResearchError as exc:
        status = str(exc)
    (private / f"{symbol}-daily-raw.json").write_text(
        json.dumps(raw_pages, ensure_ascii=False), encoding="utf-8"
    )
    valid: list[list[str | float]] = []
    invalid = 0
    for day, row in sorted(collected.items()):
        try:
            op, high, low, close, volume = (
                float(str(row.get(key, "nan")))
                for key in ("open", "high", "low", "clos", "tvol")
            )
            if (
                not all(math.isfinite(v) for v in (op, high, low, close, volume))
                or min(op, high, low, close) <= 0
                or volume < 0
                or not low <= min(op, close) <= max(op, close) <= high
            ):
                raise ValueError
            local = datetime.strptime(day, "%Y%m%d").replace(
                hour=16, tzinfo=ZoneInfo("America/New_York")
            )
            valid.append(
                [
                    symbol,
                    local.astimezone(timezone.utc).isoformat(),
                    op,
                    high,
                    low,
                    close,
                    volume,
                ]
            )
        except ValueError:
            invalid += 1
    with (private / f"{symbol}-daily.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("symbol", "timestamp", "open", "high", "low", "close", "volume")
        )
        writer.writerows(valid)
    dates = sorted(collected)
    return {
        "symbol": symbol,
        "status": status,
        "rows": len(valid),
        "first_session": dates[0] if dates else None,
        "last_session": dates[-1] if dates else None,
        "duplicate_rows": duplicates,
        "invalid_ohlcv_rows": invalid,
        "warmup_306_satisfied": len(valid) >= 306,
        "timeframe": "1Day",
        "MODP_requested": "1",
        "adjustment_definition_independently_verified": False,
        "split_events_available": False,
    }
