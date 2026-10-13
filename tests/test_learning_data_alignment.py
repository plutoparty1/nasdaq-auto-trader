from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.backtest_market_data import (
    validate_backtest_market_data,
)
from nasdaq_auto_trader.ai_quant_lab.operator_models import OperatorPaths
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.learning_data import collect_completed_learning_bars
from nasdaq_auto_trader.learning_data_alignment import prepare_learning_data
from nasdaq_auto_trader.learning_runner import run_learning_only
from nasdaq_auto_trader.models import Bar
from nasdaq_auto_trader.quant_data.features import PriceBar


def bars(symbol: str, dates: tuple[str, ...]) -> list[PriceBar]:
    return [PriceBar(symbol, date, 100, 102, 99, 101, 1000) for date in dates]


DATES = ("2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26")


def test_different_history_starts_use_common_range_without_changing_prices() -> None:
    raw = {"AAPL": bars("AAPL", DATES), "MSFT": bars("MSFT", DATES[1:])}
    assert validate_backtest_market_data(raw, 1000)[1] == "market_data_timestamps_misaligned"
    prepared = prepare_learning_data(raw)
    assert prepared.reason is None
    assert prepared.bars["AAPL"] == raw["AAPL"][1:]
    assert prepared.bars["MSFT"] == raw["MSFT"]
    assert validate_backtest_market_data(prepared.bars, 1000) == (4, None)
    assert len(raw["AAPL"]) == 5
    assert any("2026-06-23" in line and "2026-06-26" in line for line in prepared.diagnostics)


def test_internal_missing_day_is_blocked_and_identified() -> None:
    raw = {"AAPL": bars("AAPL", DATES), "MSFT": bars("MSFT", DATES[:2] + DATES[3:])}
    prepared = prepare_learning_data(raw)
    assert prepared.reason == "market_data_timestamps_misaligned"
    assert prepared.bars == raw
    assert any("MSFT" in line and "2026-06-24" in line for line in prepared.diagnostics)


def test_stale_tail_is_not_silently_trimmed_from_all_symbols() -> None:
    prepared = prepare_learning_data({"AAPL": bars("AAPL", DATES), "MSFT": bars("MSFT", DATES[:-1])})
    assert prepared.reason == "market_data_timestamps_misaligned"
    assert any("MSFT" in line and "2026-06-26" in line for line in prepared.diagnostics)


def test_missing_symbol_is_preserved_and_reported() -> None:
    prepared = prepare_learning_data({"AAPL": bars("AAPL", DATES), "MSFT": []})
    assert prepared.reason == "market_data_missing"
    assert "MSFT" in prepared.bars
    assert any("MSFT" in line and "0" in line for line in prepared.diagnostics)


def test_duplicate_or_unordered_timestamps_are_not_hidden_by_trimming() -> None:
    for dates in (DATES[:1] + DATES, tuple(reversed(DATES))):
        prepared = prepare_learning_data({"AAPL": bars("AAPL", dates), "MSFT": bars("MSFT", DATES[1:])})
        assert prepared.reason == "market_data_timestamps_not_monotonic"


def test_invalid_prices_in_trimmed_prefix_remain_blocked() -> None:
    invalid = bars("AAPL", DATES)
    invalid[0] = replace(invalid[0], close=float("nan"))
    prepared = prepare_learning_data({"AAPL": invalid, "MSFT": bars("MSFT", DATES[1:])})
    assert prepared.reason == "market_data_values_invalid"


def test_equivalent_timezone_instants_are_aligned() -> None:
    utc = tuple(f"{day}T20:00:00Z" for day in DATES)
    eastern = tuple(f"{day}T16:00:00-04:00" for day in DATES[1:])
    prepared = prepare_learning_data({"AAPL": bars("AAPL", utc), "MSFT": bars("MSFT", eastern)})
    assert prepared.reason is None
    assert validate_backtest_market_data(prepared.bars, 1000) == (4, None)


def test_too_short_overlap_remains_blocked() -> None:
    prepared = prepare_learning_data({"AAPL": bars("AAPL", DATES[:3]), "MSFT": bars("MSFT", DATES[2:])})
    assert prepared.reason is not None


class IncompleteProvider:
    def get_stock_bars(self, symbols: list[str], timeframe: str, start: str,
                       end: str | None = None, limit: int = 1000) -> dict[str, list[Bar]]:
        return {"AAPL": [Bar("AAPL", day, 100, 102, 99, 101, 1000)
                         for day in DATES if end is None or day <= end]}


def test_collection_preserves_missing_requested_symbols() -> None:
    collected = collect_completed_learning_bars(
        AppConfig(symbols=["AAPL", "MSFT"]), IncompleteProvider(),
        datetime(2026, 6, 27, tzinfo=timezone.utc),
    )
    assert collected["MSFT"] == []


def test_runner_preserves_gap_diagnostics_without_research_artifacts(tmp_path: Path) -> None:
    paths = OperatorPaths(tmp_path / "config.json", tmp_path / "registry.json",
                          tmp_path / "promoted.json", tmp_path / "specs", tmp_path / "audit.jsonl")
    result = run_learning_only(paths, {"AAPL": bars("AAPL", DATES), "MSFT": bars("MSFT", DATES[:2] + DATES[3:])})
    assert result.status == "blocked"
    assert result.submitted_orders == 0
    assert result.generated_candidates == 0
    assert any("MSFT" in line and "2026-06-24" in line for line in result.data_diagnostics)
    assert not paths.registry_path.exists()
    assert not paths.ai_config_path.exists()


def test_runner_research_uses_trimmed_data_without_live_promotion(tmp_path: Path) -> None:
    from tests.test_learning_runner import _bars

    raw = _bars()
    raw["AAPL"] = raw["AAPL"][1:]
    paths = OperatorPaths(tmp_path / "config.json", tmp_path / "registry.json",
                          tmp_path / "promoted.json", tmp_path / "specs", tmp_path / "audit.jsonl")
    result = run_learning_only(paths, raw)
    assert result.status == "completed"
    assert "market_data_timestamps_misaligned" not in result.reasons
    assert "independent_validation_required" in result.reasons
    assert result.accepted_candidates == 0
    assert result.submitted_orders == 0
    assert any("319" in line for line in result.data_diagnostics)
    assert not paths.promoted_path.exists()
