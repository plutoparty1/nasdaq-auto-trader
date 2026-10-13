from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .ai_quant_lab.backtest_market_data import validate_backtest_market_data
from .ai_quant_lab.operator_market_data import BarsBySymbol
from .quant_data.feature_statistics import normalized_timestamps


@dataclass(frozen=True, slots=True)
class PreparedLearningData:
    bars: BarsBySymbol
    reason: str | None
    diagnostics: tuple[str, ...]


def prepare_learning_data(bars: BarsBySymbol) -> PreparedLearningData:
    """Trim surplus leading history; never fill prices or bridge missing dates."""
    if not bars:
        return PreparedLearningData(bars, "market_data_missing", ())
    timestamps_by_symbol: dict[str, tuple[datetime, ...]] = {}
    for symbol, history in bars.items():
        if not history:
            return PreparedLearningData(bars, "market_data_missing", (f"{symbol}: 일봉 0개 (시세 응답 없음)",))
        _, reason = validate_backtest_market_data({symbol: history}, 100_000.0)
        if reason:
            return PreparedLearningData(bars, reason, (f"{symbol}: 일봉 {len(history)}개, 원본 데이터 검사 실패",))
        timestamps = normalized_timestamps(history)
        if timestamps is None:
            return PreparedLearningData(bars, "market_data_timestamp_invalid", (f"{symbol}: 일봉 날짜 해석 실패",))
        timestamps_by_symbol[symbol] = timestamps

    common_start = max(times[0] for times in timestamps_by_symbol.values())
    required_dates = {
        stamp for times in timestamps_by_symbol.values()
        for stamp in times if stamp >= common_start
    }
    diagnostics: list[str] = []
    for symbol, times in timestamps_by_symbol.items():
        missing = sorted(required_dates.difference(times))
        if missing:
            sample = ", ".join(stamp.isoformat() for stamp in missing[:5])
            diagnostics.append(
                f"{symbol}: 일봉 {len(times)}개 ({times[0].date()} ~ {times[-1].date()}), "
                f"누락 {len(missing)}개: {sample}"
            )
    if diagnostics:
        return PreparedLearningData(bars, "market_data_timestamps_misaligned", tuple(diagnostics))

    aligned = {
        symbol: [bar for bar, stamp in zip(history, timestamps_by_symbol[symbol], strict=True)
                 if stamp >= common_start]
        for symbol, history in bars.items()
    }
    count, reason = validate_backtest_market_data(aligned, 100_000.0)
    end = max(required_dates)
    removed = sum(len(bars[symbol]) - len(history) for symbol, history in aligned.items())
    summary = (
        f"{len(aligned)}개 종목, 종목당 {count if reason is None else len(next(iter(aligned.values())))}개 일봉, "
        f"공통 기간 {common_start.date()} ~ {end.date()}, 이전 일봉 {removed}개 제외"
    )
    return PreparedLearningData(aligned, reason, (summary,))
