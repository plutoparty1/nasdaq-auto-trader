from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from .automatic_selection import (
    BatchQuoteMarketData,
    BestQuoteMarketData,
    KISLiquidityMarketData,
    SelectionMarketData,
)
from .config import AppConfig
from .market_hours import latest_completed_market_date
from .quant_data.features import PriceBar
from .quant_data.market_quality import filter_tradeable_symbols
from .quant_data.universe_snapshot import load_default_universe
from .ai_quant_lab.types import JsonObject
from .models import Bar


@runtime_checkable
class ShadowMarketData(SelectionMarketData, Protocol):
    pass


class KISShadowSource(
    KISLiquidityMarketData,
    BestQuoteMarketData,
    SelectionMarketData,
    Protocol,
):
    pass


class BatchShadowSource(
    BatchQuoteMarketData,
    SelectionMarketData,
    Protocol,
):
    pass


@dataclass(frozen=True, slots=True)
class BasicOrderlessMarketData:
    source: SelectionMarketData

    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        return self.source.get_stock_bars(symbols, timeframe, start, end, limit)


@dataclass(frozen=True, slots=True)
class KISOrderlessMarketData(BasicOrderlessMarketData):
    source: KISShadowSource

    def get_liquid_overseas_symbols(
        self,
        universe: set[str],
        limit: int = 30,
    ) -> tuple[str, ...]:
        return self.source.get_liquid_overseas_symbols(universe, limit)

    def get_best_quote(self, symbol: str) -> JsonObject:
        return self.source.get_best_quote(symbol)


@dataclass(frozen=True, slots=True)
class BatchOrderlessMarketData(BasicOrderlessMarketData):
    source: BatchShadowSource

    def get_latest_quotes(self, symbols: list[str]) -> dict[str, JsonObject]:
        return self.source.get_latest_quotes(symbols)


def orderless_market_data_view(
    market_data: SelectionMarketData,
) -> ShadowMarketData:
    if (
        isinstance(market_data, KISLiquidityMarketData)
        and isinstance(market_data, BestQuoteMarketData)
    ):
        return KISOrderlessMarketData(market_data)
    if isinstance(market_data, BatchQuoteMarketData):
        return BatchOrderlessMarketData(market_data)
    return BasicOrderlessMarketData(market_data)


@dataclass(frozen=True, slots=True)
class IntradayShadowScanReport:
    started_at: datetime
    universe_id: str
    scanned_symbols: tuple[str, ...]
    eligible_symbols: tuple[str, ...]
    rejected: dict[str, tuple[str, ...]]
    submitted_order: bool
    report_path: Path

    def to_json_object(self) -> dict[str, str | bool | list[str] | dict[str, list[str]]]:
        return {
            "started_at": self.started_at.astimezone(timezone.utc).isoformat(),
            "universe_id": self.universe_id,
            "scanned_symbols": list(self.scanned_symbols),
            "eligible_symbols": list(self.eligible_symbols),
            "rejected": {
                symbol: list(reasons) for symbol, reasons in self.rejected.items()
            },
            "submitted_order": self.submitted_order,
        }


def run_intraday_shadow_scan(
    config: AppConfig,
    market_data: ShadowMarketData,
    now: datetime,
    report_path: Path,
) -> IntradayShadowScanReport:
    snapshot = load_default_universe()
    universe = {item.symbol for item in snapshot.symbols}
    symbols = _shortlist(config, market_data, universe)
    completed_date = latest_completed_market_date(now)
    end = datetime.fromisoformat(completed_date).replace(tzinfo=timezone.utc)
    start = end - timedelta(days=max(config.lookback_days, 45))
    raw_bars = market_data.get_stock_bars(
        symbols,
        config.timeframe,
        start.date().isoformat(),
        completed_date,
        min(config.bar_limit, 320),
    )
    quotes = _quotes(market_data, symbols)
    price_bars = {
        symbol: [
            PriceBar(
                symbol=bar.symbol,
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                bid=quotes.get(symbol, (0.0, 0.0))[0]
                if index == len(bars) - 1
                else 0.0,
                ask=quotes.get(symbol, (0.0, 0.0))[1]
                if index == len(bars) - 1
                else 0.0,
            )
            for index, bar in enumerate(bars)
        ]
        for symbol, bars in raw_bars.items()
    }
    quality = filter_tradeable_symbols(
        price_bars,
        now=now,
        quotes_required=config.mode != "dry_run",
    )
    report = IntradayShadowScanReport(
        started_at=now,
        universe_id=snapshot.universe_id,
        scanned_symbols=tuple(symbols),
        eligible_symbols=quality.symbols,
        rejected=quality.rejected,
        submitted_order=False,
        report_path=report_path,
    )
    _save_report(report)
    return report


def _shortlist(
    config: AppConfig,
    market_data: ShadowMarketData,
    universe: set[str],
) -> list[str]:
    if config.broker == "kis" and isinstance(market_data, KISLiquidityMarketData):
        return list(market_data.get_liquid_overseas_symbols(universe, 30))
    return sorted(universe)


def _quotes(
    market_data: ShadowMarketData,
    symbols: list[str],
) -> dict[str, tuple[float, float]]:
    if isinstance(market_data, BatchQuoteMarketData):
        payloads = market_data.get_latest_quotes(symbols)
        return _parsed_quote_payloads(payloads)
    if isinstance(market_data, BestQuoteMarketData):
        payloads = {
            symbol: market_data.get_best_quote(symbol) for symbol in symbols
        }
        return _parsed_quote_payloads(payloads)
    return {}


def _parsed_quote_payloads(
    payloads: dict[str, JsonObject],
) -> dict[str, tuple[float, float]]:
    return {
        symbol: (
            _quote_value(payload, "bid_price", "bp", "pbid1", "bid"),
            _quote_value(payload, "ask_price", "ap", "pask1", "ask"),
        )
        for symbol, payload in payloads.items()
    }


def _quote_value(payload: JsonObject, *keys: str) -> float:
    for key in keys:
        value = payload.get(key)
        try:
            parsed = (
                float(str(value).replace(",", ""))
                if value is not None
                else 0.0
            )
        except (TypeError, ValueError):
            continue
        if parsed > 0 and math.isfinite(parsed):
            return parsed
    return 0.0


def _save_report(report: IntradayShadowScanReport) -> None:
    report.report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report.report_path.with_suffix(report.report_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report.to_json_object(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, report.report_path)
