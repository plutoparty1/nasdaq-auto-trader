from __future__ import annotations


def _unique_symbols(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for symbol in symbols:
        normalized = str(symbol).upper().strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _first_float(
    primary: dict,
    secondary: dict,
    *keys: str,
    default: float = 0.0,
) -> float:
    for payload in (primary, secondary):
        if not isinstance(payload, dict):
            continue
        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            try:
                return float(str(value).replace(",", ""))
            except ValueError:
                continue
    return default


def _first_text(
    primary: dict,
    secondary: dict,
    *keys: str,
    default: str = "",
) -> str:
    for payload in (primary, secondary):
        if not isinstance(payload, dict):
            continue
        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            return str(value).strip()
    return default


def _spread_pct(bid: float, ask: float) -> float:
    if bid <= 0 or ask <= 0:
        return 0.0
    midpoint = (bid + ask) / 2
    if midpoint <= 0:
        return 0.0
    return (ask - bid) / midpoint * 100


def _pct_range(high: float, low: float, price: float) -> float:
    if high <= 0 or low <= 0 or price <= 0 or high < low:
        return 0.0
    return (high - low) / price * 100


def _change_pct(price: float, base: float) -> float:
    if price <= 0 or base <= 0:
        return 0.0
    return (price / base - 1) * 100


def _candidate_score(
    day_range_pct: float,
    dollar_volume: float,
    spread_pct: float,
) -> float:
    liquidity_score = min(dollar_volume / 100_000_000, 2.0)
    return day_range_pct + liquidity_score - spread_pct * 2
