from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, unique

from .types import JsonObject


@unique
class StrategyFamily(StrEnum):
    TREND_FOLLOWING = "trend_following"
    CROSS_SECTIONAL_MOMENTUM = "cross_sectional_momentum"
    TIME_SERIES_MOMENTUM = "time_series_momentum"
    MEAN_REVERSION = "mean_reversion"
    BOLLINGER_ZSCORE = "bollinger_zscore"
    RSI_OSCILLATOR = "rsi_oscillator"
    VOLATILITY_BREAKOUT = "volatility_breakout"
    BREAKOUT = "breakout"
    PAIR_TRADING_STAT_ARB = "pair_trading_stat_arb"
    FACTOR_STRATEGY = "factor_strategy"
    SECTOR_THEME_ROTATION = "sector_theme_rotation"
    VOLATILITY_TARGETING = "volatility_targeting"
    ENSEMBLE = "ensemble"


@unique
class SignalType(StrEnum):
    TREND_FOLLOWING = "trend_following"
    CROSS_SECTIONAL_MOMENTUM = "cross_sectional_momentum"
    TIME_SERIES_MOMENTUM = "time_series_momentum"
    MEAN_REVERSION = "mean_reversion"
    BOLLINGER_ZSCORE = "bollinger_zscore"
    RSI_OSCILLATOR = "rsi_oscillator"
    VOLATILITY_BREAKOUT = "volatility_breakout"
    BREAKOUT = "breakout"
    PAIR_TRADING_STAT_ARB = "pair_trading_stat_arb"
    FACTOR_STRATEGY = "factor_strategy"
    SECTOR_THEME_ROTATION = "sector_theme_rotation"
    VOLATILITY_TARGETING = "volatility_targeting"
    VOLATILITY_FILTER = "volatility_filter"


@dataclass(frozen=True, slots=True)
class ResearchBasis:
    provider: str
    research_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    summary: str


@dataclass(frozen=True, slots=True)
class SignalSpec:
    signal_type: SignalType
    weight: float
    parameters: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EntryRule:
    rule_type: str
    threshold: float
    top_n: int


@dataclass(frozen=True, slots=True)
class ExitRule:
    stop_loss_mode: str
    stop_loss_atr_multiple: float
    take_profit_mode: str
    take_profit_atr_multiple: float
    trailing_stop: bool
    max_holding_days: int


@dataclass(frozen=True, slots=True)
class PositionSizingSpec:
    method: str
    risk_per_trade_pct: float
    confidence_adjusted: bool
    max_single_position_pct: float


@dataclass(frozen=True, slots=True)
class RiskControls:
    use_kill_switch: bool
    block_if_data_stale: bool
    block_if_spread_abnormal: bool
    block_if_daily_loss_limit: bool
    block_before_market_close: bool


@dataclass(frozen=True, slots=True)
class StrategySpec:
    strategy_id: str
    version: str
    strategy_family: StrategyFamily
    description: str
    research_basis: ResearchBasis
    signals: tuple[SignalSpec, ...]
    entry_rule: EntryRule
    exit_rule: ExitRule
    position_sizing: PositionSizingSpec
    risk_controls: RiskControls
    created_at: str
    raw: JsonObject


@dataclass(frozen=True, slots=True)
class StrategySpecValidation:
    valid: bool
    spec: StrategySpec | None
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def allowed_strategy_families() -> tuple[str, ...]:
    return tuple(item.value for item in StrategyFamily)


def allowed_signal_types() -> tuple[str, ...]:
    return tuple(item.value for item in SignalType)


from .strategy_schema_validation import parse_strategy_spec_json, validate_strategy_spec
