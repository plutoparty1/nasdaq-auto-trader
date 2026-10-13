"""Explicit offline experiment inputs, independent of runtime config and secrets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from math import isfinite
from pathlib import Path

from .strategy_config import StrategyConfig


@dataclass(frozen=True, slots=True)
class ExperimentInputError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class CostScenario:
    name: str
    commission_pct: float
    minimum_commission: float
    spread_bps: float
    slippage_bps: float
    source: str


@dataclass(frozen=True, slots=True)
class ExperimentSettings:
    dry_run: bool
    broker: str
    starting_krw: float
    max_position_pct: float
    max_total_position_pct: float
    cash_buffer_pct: float
    max_portfolio_risk_pct: float
    monthly_loss_stop_pct: float
    costs: tuple[CostScenario, ...]
    strategy: StrategyConfig = field(default_factory=StrategyConfig)


@dataclass(frozen=True, slots=True)
class DataProvenance:
    data_source: str
    bar_interval: str
    universe_source: str
    universe_as_of: str
    survivorship_corrected: bool
    synthetic: bool
    adjustment_policy: str


def _read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_settings(path: Path) -> ExperimentSettings:
    raw = _read_json(path)
    required = {
        "dry_run",
        "broker",
        "starting_krw",
        "max_position_pct",
        "max_total_position_pct",
        "cash_buffer_pct",
        "max_portfolio_risk_pct",
        "monthly_loss_stop_pct",
        "costs",
        "strategy",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise ExperimentInputError(
            "experiment fields must match the offline schema exactly"
        )
    if raw["dry_run"] is not True or raw["broker"] != "offline_csv":
        raise ExperimentInputError("dry_run=true and broker=offline_csv are mandatory")
    for name in (
        "max_position_pct",
        "max_total_position_pct",
        "cash_buffer_pct",
        "max_portfolio_risk_pct",
        "monthly_loss_stop_pct",
    ):
        value = raw[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or not 0 < value < 1
        ):
            raise ExperimentInputError(
                f"{name} must be a decimal fraction between zero and one"
            )
    if raw["starting_krw"] != 80000:
        raise ExperimentInputError(
            "this prespecified experiment starts with exactly 80000 KRW"
        )
    scenarios = tuple(CostScenario(**cost) for cost in raw["costs"])
    if len(scenarios) != 2 or {cost.name for cost in scenarios} != {"base", "stress"}:
        raise ExperimentInputError(
            "exactly base and stress cost scenarios are required"
        )
    for cost in scenarios:
        for value in (
            cost.commission_pct,
            cost.minimum_commission,
            cost.spread_bps,
            cost.slippage_bps,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ExperimentInputError(
                    "cost assumptions must be finite and nonnegative"
                )
        if (
            cost.commission_pct >= 1
            or (cost.spread_bps / 2 + cost.slippage_bps) >= 10000
        ):
            raise ExperimentInputError(
                "commission and execution impact must be fractions below one"
            )
        if not isinstance(cost.source, str) or not cost.source.strip():
            raise ExperimentInputError("cost source or assumption label is required")
    try:
        strategy = StrategyConfig(**raw["strategy"])
    except TypeError as error:
        raise ExperimentInputError("unknown strategy field") from error
    for item in fields(strategy):
        value = getattr(strategy, item.name)
        default = item.default
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ExperimentInputError(f"{item.name} must be a boolean")
        elif isinstance(default, int):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ExperimentInputError(f"{item.name} must be a positive integer")
        elif isinstance(default, float) and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value < 0
        ):
            raise ExperimentInputError(
                f"{item.name} must be a nonnegative finite number"
            )
        if item.name.endswith("_pct") and not 0 < value < 1:
            raise ExperimentInputError(
                f"{item.name} must be a decimal fraction in (0, 1)"
            )
    return ExperimentSettings(
        raw["dry_run"],
        raw["broker"],
        raw["starting_krw"],
        raw["max_position_pct"],
        raw["max_total_position_pct"],
        raw["cash_buffer_pct"],
        raw["max_portfolio_risk_pct"],
        raw["monthly_loss_stop_pct"],
        scenarios,
        strategy,
    )


def load_provenance(path: Path) -> DataProvenance:
    try:
        result = DataProvenance(**_read_json(path))
    except TypeError as error:
        raise ExperimentInputError(
            "data provenance fields do not match schema"
        ) from error
    if result.bar_interval != "1Day":
        raise ExperimentInputError("these frozen candidate policies require 1Day bars")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            result.data_source,
            result.universe_source,
            result.universe_as_of,
            result.adjustment_policy,
        )
    ):
        raise ExperimentInputError(
            "data, universe, timestamp and adjustment provenance are required"
        )
    return result
