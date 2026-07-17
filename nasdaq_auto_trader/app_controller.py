from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from inspect import Parameter, signature
from pathlib import Path
from typing import Any, Callable

from .app_types import AppConfigurationError, AutoTradeState, EngineResult, PortfolioSnapshot
from .config import AppConfig, validate_trading_mode
from .config_errors import TradingModeValidationError
from .config_manager import (
    SettingsError,
    TradingSessionState,
    TradingSettings,
    apply_settings_to_app_config,
    default_settings_path,
    validate_settings,
)
from .engine import TradingEngine
from .engine_errors import PreOrderCycleError
from .controller_operations import ControllerOperationsMixin
from .intraday_shadow_scan import IntradayShadowScanReport
from .portfolio_presenter import position_to_row
from .quant_data.resources import application_data_root
from .quant_data.symbol_selector import SelectionReport
from .selection_health import AutomaticSelectionHealth
from .session_state_persistence import load_session_state, save_session_state
from .trading_session_store import SessionStoreError, TradingSessionStore
from .runtime_journal import NullRuntimeJournal, RuntimeJournalWriter
from .controller_runtime_recorder import ControllerRuntimeRecorder
from .unattended_result_policy import terminal_order_failure_reason
from .unattended_policy import is_recoverable_preorder_failure


class AutoTradeController(ControllerOperationsMixin):
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
        runtime_journal: RuntimeJournalWriter | None = None,
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
        self.runtime_journal = runtime_journal or NullRuntimeJournal()
        self.runtime_recorder = ControllerRuntimeRecorder(self.runtime_journal)
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
        self.last_shadow_scan: IntradayShadowScanReport | None = None
        self._selection_health = AutomaticSelectionHealth()
        self._initialize_operations()

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

        try:
            engine = self._create_engine()
            results = engine.run_once()
            report = getattr(engine, "last_selection_report", None)
            if isinstance(report, SelectionReport):
                self.last_selection_report = report
                self._selection_health = self._selection_health.observe(report)
            else:
                self.last_selection_report = None
            if self.trading_settings.auto_symbol_selection_enabled:
                save_session_state(self.session_store, self.session_state)
        except PreOrderCycleError:
            raise
        except Exception as exc:  # noqa: BROAD_EXCEPT_OK
            with self._lock:
                self.last_error = str(exc)
                should_pause = (
                    self.trading_settings.unattended_operation_enabled
                    or self.trading_settings.stop_on_order_error
                )
                if should_pause:
                    self.state = "paused"
                    self.next_run_at = None
            raise

        terminal_reason = terminal_order_failure_reason(results)
        with self._lock:
            self.last_run_at = now
            self.last_results = results
            if (
                self.trading_settings.unattended_operation_enabled
                and terminal_reason is not None
            ):
                self.state = "paused"
                self.next_run_at = None
                self.last_error = terminal_reason
            else:
                self.next_run_at = now + timedelta(seconds=interval_seconds)
                self.last_error = self.selection_error
        self.runtime_recorder.trading_cycle(now, self.state, len(results))
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
            positions=[position_to_row(position) for position in positions.values()],
        )
        with self._lock:
            self.last_snapshot = snapshot
            preserve_retry = bool(
                self.last_error
                and self.trading_settings.unattended_operation_enabled
                and is_recoverable_preorder_failure(self.last_error)
            )
            if not preserve_retry and (self.state != "paused" or self.last_error is None):
                self.last_error = self.selection_error
        self.runtime_recorder.portfolio(snapshot)
        return snapshot

    def _create_engine(self):
        engine_kwargs = {}
        if _factory_accepts_argument(self._engine_factory, "trading_settings"):
            engine_kwargs["trading_settings"] = self.trading_settings
        if _factory_accepts_argument(self._engine_factory, "trading_session_state"):
            engine_kwargs["trading_session_state"] = self.session_state
        if _factory_accepts_argument(self._engine_factory, "live_order_confirmation"):
            unattended_live_allowed = (
                not self.trading_settings.unattended_operation_enabled
                or self.trading_settings.unattended_live_trading_enabled
            )
            engine_kwargs["live_order_confirmation"] = (
                self.config.mode == "live" and unattended_live_allowed
            )
        return self._engine_factory(self.config, **engine_kwargs)

    def _ensure_settings_valid(self) -> None:
        if self.settings_error:
            raise SettingsError(self.settings_error)
        if self.session_error:
            raise SettingsError(self.session_error)
        result = validate_settings(self.trading_settings)
        if not result.ok:
            raise SettingsError("\n".join(result.errors))
        if self.config.allow_live_trading:
            try:
                validate_trading_mode(self.config)
            except TradingModeValidationError as exc:
                raise SettingsError(str(exc)) from exc

def _factory_accepts_argument(factory: Callable[..., Any], name: str) -> bool:
    try:
        parameters = signature(factory).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == name or parameter.kind == Parameter.VAR_KEYWORD
        for parameter in parameters
    )
