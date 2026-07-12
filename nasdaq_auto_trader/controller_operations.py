from __future__ import annotations

from dataclasses import replace
from datetime import timedelta, timezone

from .ai_quant_lab.artifact_paths import default_strategy_artifact_paths
from .app_types import EngineResult
from .automation_coordinator import AutomationCoordinator, PreflightHealth
from .dry_run_market_data import DryRunMarketData
from .learning_data import collect_completed_learning_bars
from .learning_runner import (
    LearningCancellation,
    LearningProgress,
    LearningRunResult,
    run_learning_only,
)
from .operating_state import OperatingState, OperatingStateStore
from .market_hours import EASTERN
from .quant_data.resources import application_data_root
from .quant_data.symbol_selector import StrategyResolutionBlock, resolve_strategy


class ControllerOperationsMixin:
    def _initialize_operations(self) -> None:
        self._learning_cancellation: LearningCancellation | None = None
        self.last_learning_progress: LearningProgress | None = None
        self.operating_store = OperatingStateStore(
            application_data_root() / "runtime" / "operating_state.json"
        )
        self.operating_coordinator = AutomationCoordinator(self.operating_store)

    def run_operating_cycle(self, force: bool = False) -> list[EngineResult] | None:
        with self._lock:
            if self.state != "running":
                return None
        now = self._clock()
        current = self.operating_store.load()
        market_date = now.astimezone(EASTERN).date().isoformat()
        transition = self.operating_coordinator.advance(
            now,
            self._operating_health(),
            reconciliation_complete=(
                current.last_reconciled_market_date == market_date
            ),
            new_data_available=True,
        )
        if transition.state is OperatingState.LIVE_TRADING:
            return self.run_auto_cycle(force=force)
        if transition.state is OperatingState.POST_MARKET_RECONCILIATION:
            try:
                self.refresh_portfolio()
            except Exception as exc:  # noqa: BROAD_EXCEPT_OK
                halted = self.operating_coordinator.safe_halt(
                    "account_state_unavailable",
                    now,
                )
                with self._lock:
                    self.state = "paused"
                    self.last_error = f"{halted.reason}:{type(exc).__name__}"
                return []
            reconciled = self.operating_store.load()
            self.operating_store.save(
                replace(
                    reconciled,
                    last_reconciled_market_date=market_date,
                )
            )
        if transition.state is OperatingState.OFF_HOURS_LEARNING:
            self._execute_learning(
                LearningCancellation(self._record_learning_progress)
            )
        if transition.state in (
            OperatingState.SAFE_HALT,
            OperatingState.EMERGENCY_STOP,
        ):
            with self._lock:
                self.state = "paused"
                self.last_error = transition.reason
        with self._lock:
            self.last_run_at = now
            self.next_run_at = now + timedelta(seconds=self.interval_seconds)
        return []

    def run_learning_only(
        self,
        cancellation: LearningCancellation | None = None,
    ) -> LearningRunResult:
        control = cancellation or LearningCancellation(
            self._record_learning_progress
        )
        previous_operating_state = self.operating_store.load()
        self.operating_store.save(
            replace(
                previous_operating_state,
                state=OperatingState.MANUAL_TRAIN_ONLY,
                entered_at=self._clock().astimezone(timezone.utc),
            )
        )
        with self._lock:
            previous_state = self.state
            self.state = "paused" if previous_state == "running" else previous_state
            self._learning_cancellation = control
        try:
            return self._execute_learning(control)
        finally:
            safe_state = (
                previous_operating_state.state
                if previous_operating_state.state
                in (OperatingState.SAFE_HALT, OperatingState.EMERGENCY_STOP)
                else OperatingState.IDLE
            )
            self.operating_store.save(
                replace(
                    previous_operating_state,
                    state=safe_state,
                    entered_at=self._clock().astimezone(timezone.utc),
                    active_job_key=None,
                )
            )
            with self._lock:
                self._learning_cancellation = None

    def cancel_learning(self) -> None:
        with self._lock:
            cancellation = self._learning_cancellation
        if cancellation is not None:
            cancellation.cancel()

    def _record_learning_progress(self, progress: LearningProgress) -> None:
        with self._lock:
            self.last_learning_progress = progress

    def _execute_learning(
        self,
        control: LearningCancellation,
    ) -> LearningRunResult:
        engine = self._create_engine()
        if isinstance(engine.market_data, DryRunMarketData):
            return run_learning_only(bars_by_symbol={}, cancellation=control)
        bars = collect_completed_learning_bars(
            self.config,
            engine.market_data,
            self._clock(),
        )
        return run_learning_only(bars_by_symbol=bars, cancellation=control)

    def _operating_health(self) -> PreflightHealth:
        if not self.trading_settings.auto_symbol_selection_enabled:
            return PreflightHealth(
                risk_config_ok=self.settings_error is None and self.session_error is None,
            )
        paths = default_strategy_artifact_paths()
        mode = "live" if self.config.mode == "live" else "paper"
        resolution = resolve_strategy(mode, paths)
        return PreflightHealth(
            model_ok=not isinstance(resolution, StrategyResolutionBlock),
            risk_config_ok=self.settings_error is None and self.session_error is None,
        )
