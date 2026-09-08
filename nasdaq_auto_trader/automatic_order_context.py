from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from .ai_quant_lab.artifact_paths import StrategyArtifactPaths
from .automatic_order_types import AutomaticOrderContext
from .automatic_risk import AutomaticRiskLimits
from .automatic_risk_config import learned_risk_config_digest
from .config import AppConfig
from .config_manager import TradingSessionState, TradingSettings
from .live_authorization import risk_config_digest
from .models import Bar
from .quant_data.symbol_selector import SelectionReport


class AutomaticContextSource(Protocol):
    config: AppConfig
    trading_settings: TradingSettings | None
    last_selection_report: SelectionReport | None
    automatic_risk_limits: AutomaticRiskLimits | None
    trading_session_state: TradingSessionState
    strategy_artifact_paths: StrategyArtifactPaths
    _clock: Callable[[], datetime]


def automatic_order_context(
    engine: AutomaticContextSource,
    bars: list[Bar],
) -> AutomaticOrderContext | None:
    report = engine.last_selection_report
    settings = engine.trading_settings
    if report is None or settings is None:
        return None
    signal_timestamp = bars[-1].timestamp if bars else ""
    if len(signal_timestamp) == 8 and signal_timestamp.isdigit():
        interval_seconds = settings.unattended_interval_minutes * 60
        cycle_number = int(engine._clock().timestamp()) // interval_seconds
        cycle_start = datetime.fromtimestamp(
            cycle_number * interval_seconds,
            timezone.utc,
        )
        signal_timestamp = f"{signal_timestamp}@{cycle_start.isoformat()}"
    return AutomaticOrderContext(
        strategy_id=report.strategy_id,
        strategy_version=report.strategy_version,
        strategy_digest=report.strategy_digest,
        universe_id=report.universe_id,
        universe_effective_date=report.universe_effective_date,
        universe_version=report.universe_version,
        risk_digest=risk_config_digest(
            engine.config,
            engine.strategy_artifact_paths,
        ),
        mode=engine.config.mode,
        signal_timestamp=signal_timestamp,
        max_daily_buy_count=settings.max_daily_buy_count,
        max_daily_sell_count=settings.max_daily_sell_count,
        max_daily_order_count=(
            engine.automatic_risk_limits.max_orders_per_day
            if engine.automatic_risk_limits is not None
            else 2**31 - 1
        ),
        cooldown_minutes=(
            settings.cooldown_minutes if settings.cooldown_enabled else 0
        ),
        daily_loss_breached=engine.trading_session_state.daily_loss_breached,
        daily_loss_state_unavailable=(
            engine.trading_session_state.daily_loss_state_unavailable
        ),
        baseline_available=engine.trading_session_state.starting_equity is not None,
        learned_risk_digest=learned_risk_config_digest(
            engine.strategy_artifact_paths.ai_config_path
        ),
    )
