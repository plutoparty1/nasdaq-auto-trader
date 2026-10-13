from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

from .market_hours import EASTERN, latest_completed_market_date
from .models import Bar, TradeDecision
from .session_claims import ClaimStatus, SignalKey
from .trading_session_store import SessionStoreError, TradingSessionStore


def _bar_date(timestamp: str) -> date:
    if len(timestamp) == 8 and timestamp.isdigit():
        return datetime.strptime(timestamp, "%Y%m%d").date()
    if len(timestamp) == 10:
        return date.fromisoformat(timestamp)
    parsed = datetime.fromisoformat(timestamp)
    return parsed.astimezone(EASTERN).date() if parsed.tzinfo else parsed.date()


def prepare_completed_bars(bars: Sequence[Bar], timeframe: str, now: datetime) -> list[Bar]:
    normalized = now.replace(tzinfo=UTC) if now.tzinfo is None else now
    if timeframe.casefold() in {"1day", "day", "1d"}:
        cutoff = latest_completed_market_date(normalized)
        if not cutoff:
            return []
        completed_date = date.fromisoformat(cutoff)
        result: list[Bar] = []
        for bar in bars:
            try:
                if _bar_date(bar.timestamp) <= completed_date:
                    result.append(bar)
            except ValueError:
                continue
        return result
    interval = re.fullmatch(r"([1-9][0-9]*)(Min|Hour)", timeframe, re.IGNORECASE)
    if interval is None:
        return []
    units = int(interval.group(1))
    duration = timedelta(minutes=units) if interval.group(2).casefold() == "min" else timedelta(hours=units)
    result = []
    for bar in bars:
        try:
            timestamp = datetime.fromisoformat(bar.timestamp)
            if timestamp.tzinfo is not None and timestamp + duration <= normalized:
                result.append(bar)
        except ValueError:
            continue
    return result


def gate_decision(
    store: TradingSessionStore,
    strategy_id: str,
    strategy_version: str,
    symbol: str,
    bars: Sequence[Bar],
    decision: TradeDecision,
    now: datetime,
) -> TradeDecision:
    if not bars:
        return replace(decision, action="hold", reasons=[*decision.reasons, "no_completed_bar"])
    timestamp = bars[-1].timestamp
    try:
        bar_date = _bar_date(timestamp).isoformat()
    except ValueError:
        return replace(decision, action="hold", reasons=[*decision.reasons, "invalid_completed_bar_timestamp"])
    key = SignalKey(bar_date, strategy_id, strategy_version, symbol, "evaluation", timestamp)
    try:
        claimed = store.claim(key)
        if not claimed.granted:
            return replace(decision, action="hold", reasons=[*decision.reasons, "completed_bar_already_evaluated", claimed.reason])
        store.complete(key, ClaimStatus.SUBMITTED)
    except SessionStoreError as exc:
        return replace(decision, action="hold", reasons=[*decision.reasons, exc.reason])
    return decision
