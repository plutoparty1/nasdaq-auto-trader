from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class UniverseCandidate:
    symbol: str
    tradable: bool = True
    halted: bool = False
    data_error: bool = False
    last_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    avg_volume_20d: float = 0.0
    dollar_volume: float = 0.0
    volatility_20d: float = 0.0
    updated_at: datetime | None = None
    sector: str = ""


@dataclass(frozen=True, slots=True)
class UniverseRejected:
    symbol: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UniverseSelection:
    selected: tuple[UniverseCandidate, ...]
    rejected: tuple[UniverseRejected, ...]


@dataclass(frozen=True, slots=True)
class UniverseFilterConfig:
    min_avg_volume_20d: float = 100_000.0
    min_dollar_volume: float = 1_000_000.0
    max_spread_bps: float = 50.0
    max_volatility_20d: float = 1.50
    stale_data_seconds: int = 60


class UniverseBuilder:
    def __init__(self, config: UniverseFilterConfig | None = None) -> None:
        self.config = config or UniverseFilterConfig()

    def filter(
        self,
        candidates: list[UniverseCandidate],
        now: datetime | None = None,
    ) -> UniverseSelection:
        effective_now = now or datetime.now(timezone.utc)
        selected: list[UniverseCandidate] = []
        rejected: list[UniverseRejected] = []
        for candidate in candidates:
            reasons = self._rejection_reasons(candidate, effective_now)
            if reasons:
                rejected.append(UniverseRejected(candidate.symbol, tuple(reasons)))
            else:
                selected.append(candidate)
        ranked = sorted(
            selected,
            key=lambda item: (item.dollar_volume, -item.volatility_20d),
            reverse=True,
        )
        return UniverseSelection(tuple(ranked), tuple(rejected))

    def _rejection_reasons(
        self,
        candidate: UniverseCandidate,
        now: datetime,
    ) -> list[str]:
        reasons: list[str] = []
        if not candidate.tradable:
            reasons.append("not_tradable")
        if candidate.halted:
            reasons.append("halted")
        if candidate.data_error:
            reasons.append("data_error")
        if candidate.last_price <= 0:
            reasons.append("invalid_price")
        if _spread_bps(candidate.bid, candidate.ask) > self.config.max_spread_bps:
            reasons.append("spread_too_wide")
        if candidate.avg_volume_20d < self.config.min_avg_volume_20d:
            reasons.append("liquidity_too_low")
        if candidate.dollar_volume < self.config.min_dollar_volume:
            reasons.append("dollar_volume_too_low")
        if candidate.volatility_20d > self.config.max_volatility_20d:
            reasons.append("volatility_extreme")
        if _is_stale(candidate.updated_at, now, self.config.stale_data_seconds):
            reasons.append("stale_data")
        return reasons


def _spread_bps(bid: float, ask: float) -> float:
    if bid <= 0 or ask <= 0 or ask < bid:
        return float("inf")
    mid = (bid + ask) / 2
    return ((ask - bid) / mid) * 10_000


def _is_stale(
    updated_at: datetime | None,
    now: datetime,
    stale_data_seconds: int,
) -> bool:
    if updated_at is None:
        return True
    return (now - updated_at).total_seconds() > stale_data_seconds
