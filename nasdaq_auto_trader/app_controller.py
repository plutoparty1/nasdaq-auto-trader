from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from inspect import Parameter, signature
from pathlib import Path
from typing import Any, Callable

from .app_types import AppConfigurationError, AutoTradeState, EngineResult, PortfolioSnapshot, PositionRow
from .config import AppConfig
from .config_manager import (
    SettingsError,
    TradingSessionState,
    TradingSettings,
    apply_settings_to_app_config,
    default_settings_path,
    validate_settings,
)
from .engine import TradingEngine
from .models import Position
from .quant_data.resources import application_data_root
from .quant_data.symbol_selector import SelectionReport
from .selection_health import AutomaticSelectionHealth
from .session_state_persistence import load_session_state, save_session_state
from .trading_session_store import SessionStoreError, TradingSessionStore


class AutoTradeController:
    """Stateful controller shared by the GUI and tests."""

    def __init__(
        self,
        config: AppConfig,
        engine_factory: Callable[..., TradingEngine] = TradingEngine,
        clock: Callable[[], datetime] | None = None,
        interval_seconds: float = 60 * 60,
        trading_settings: TradingSettings | None = None,
        settings_path: str | Path | None = None,
        settings_error: str | None = None,
        session_store: TradingSessionStore | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise AppConfigurationError("interval_seconds must be greater than zero")
        self.base_config = config
        self.settings_path = Path(settings_path) if settings_path else default_settings_path()
        self.trading_settings = trading_settings or TradingSettings()
        self.settings_error = settings_error
        self.config = apply_settings_to_app_config(self.base_config, self.trading_settings)
        self._engine_factory = engine_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self.state: AutoTradeState = "stopped"
        self.interval_seconds = float(interval_seconds)
        self.session_store = session_store or TradingSessionStore(
            application_data_root() / "runtime" / "trading_session.json"
        )
        self.session_error: str | None = None
        try:
            self.session_store.recover_interrupted_claims()
            self.session_state = load_session_state(self.session_store)
        except SessionStoreError as exc:
            self.session_state = TradingSessionState()
            self.session_error = exc.reason
        self.last_run_at: datetime | None = None
        self.next_run_at: datetime | None = None
        self.last_results: list[EngineResult] = []
        self.last_snapshot: PortfolioSnapshot | None = None
        self.last_error: str | None = None
        self.last_selection_report: SelectionReport | None = None
        self._selection_health = AutomaticSelectionHealth()

    @property
    def automatic_block_streak(self) -> int:
        return self._selection_health.block_streak

    @property
    def selection_error(self) -> str | None:
        return self._selection_health.persistent_error

    def update_settings(self, settings: TradingSettings) -> None:
        """Apply newly saved GUI settings to future engine instances."""

        result = validate_settings(settings)
        if not result.ok:
            raise SettingsError("\n".join(result.errors))
        with self._lock:
            self.trading_settings = settings
            self.config = apply_settings_to_app_config(self.base_config, settings)
            if not settings.auto_symbol_selection_enabled:
                self.last_selection_report = None
                self._selection_health = AutomaticSelectionHealth()
            self.settings_error = None

    def start(self, interval_seconds: float | None = None) -> None:
        """Start automatic trading cycles."""

        self._ensure_settings_valid()
        with self._lock:
            if interval_seconds is not None:
                if interval_seconds <= 0:
                    raise AppConfigurationError(
                        "interval_seconds must be greater than zero"
                    )
                self.interval_seconds = float(interval_seconds)
            self.state = "running"
            self.next_run_at = self._clock()

    def pause(self) -> None:
        """Pause future automatic trading cycles without closing the app."""

        with self._lock:
            if self.state == "running":
                self.state = "paused"

    def resume(self) -> None:
        """Resume automatic trading cycles."""

        self._ensure_settings_valid()
        with self._lock:
            self.state = "running"
            self.next_run_at = self._clock()

    def stop(self) -> None:
        """Stop automatic trading cycles."""

        with self._lock:
            self.state = "stopped"
            self.next_run_at = None

    def is_due(self) -> bool:
        """Return whether the next automatic cycle should run now."""

        with self._lock:
            return (
                self.state == "running"
                and self.next_run_at is not None
                and self._clock() >= self.next_run_at
            )

    def run_auto_cycle(self, force: bool = False) -> list[EngineResult] | None:
        """Run one automatic trading cycle when running and due."""

        self._ensure_settings_valid()
        with self._lock:
            if self.state != "running":
                return None
            now = self._clock()
            if not force and self.next_run_at is not None and now < self.next_run_at:
                return None
            interval_seconds = self.interval_seconds

        engine = self._create_engine()
        try:
            results = engine.run_once()
            report = getattr(engine, "last_selection_report", None)
            if isinstance(report, SelectionReport):
                self.last_selection_report = report
                self._selection_health = self._selection_health.observe(report)
            else:
                self.last_selection_report = None
            if self.trading_settings.auto_symbol_selection_enabled:
                save_session_state(self.session_store, self.session_state)
        except Exception as exc:  # noqa: BROAD_EXCEPT_OK
            with self._lock:
                self.last_error = str(exc)
                if self.trading_settings.stop_on_order_error:
                    self.state = "paused"
            raise

        with self._lock:
            self.last_run_at = now
            self.next_run_at = now + timedelta(seconds=interval_seconds)
            self.last_results = results
            self.last_error = self.selection_error
        return results

    def refresh_portfolio(self) -> PortfolioSnapshot:
        """Fetch and normalize the latest account and holdings snapshot."""

        engine = self._create_engine()
        account, positions = engine.load_portfolio(refresh=True)
        snapshot = PortfolioSnapshot(
            as_of=self._clock(),
            mode=self.config.mode,
            broker=self.config.broker,
            account=account,
            positions=[_position_to_row(position) for position in positions.values()],
        )
        with self._lock:
            self.last_snapshot = snapshot
            self.last_error = self.selection_error
        return snapshot

    def _create_engine(self):
        self._ensure_gui_mode()
        if _factory_accepts_settings(self._engine_factory):
            return self._engine_factory(
                self.config,
                trading_settings=self.trading_settings,
                trading_session_state=self.session_state,
            )
        return self._engine_factory(self.config)

    def _ensure_settings_valid(self) -> None:
        self._ensure_gui_mode()
        if self.settings_error:
            raise SettingsError(self.settings_error)
        if self.session_error:
            raise SettingsError(self.session_error)
        result = validate_settings(self.trading_settings)
        if not result.ok:
            raise SettingsError("\n".join(result.errors))

    def _ensure_gui_mode(self) -> None:
        if self.config.mode == "live":
            raise SettingsError("gui_live_trading_disabled")


def _position_to_row(position: Position) -> PositionRow:
    latest_price = None
    if position.qty > 0 and position.market_value > 0:
        latest_price = position.market_value / position.qty

    basis = position.avg_entry_price * position.qty
    unrealized_pl = None
    unrealized_pl_pct = None
    if basis > 0 and position.market_value > 0:
        unrealized_pl = position.market_value - basis
        unrealized_pl_pct = (unrealized_pl / basis) * 100

    return PositionRow(
        symbol=position.symbol,
        qty=round(position.qty, 8),
        avg_entry_price=round(position.avg_entry_price, 4),
        market_value=round(position.market_value, 4),
        latest_price=_round_optional(latest_price, 4),
        unrealized_pl=_round_optional(unrealized_pl, 4),
        unrealized_pl_pct=_round_optional(unrealized_pl_pct, 4),
    )


def _factory_accepts_settings(factory: Callable[..., Any]) -> bool:
    try:
        parameters = signature(factory).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "trading_settings" or parameter.kind == Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def _round_optional(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)
