from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .ai_quant_lab.artifact_paths import default_strategy_artifact_paths
from .app_types import EngineResult
from .automation_coordinator import AutomationCoordinator, PreflightHealth
from .brokers.common import BrokerRequestError
from .dry_run_market_data import DryRunMarketData
from .engine_errors import PreOrderCycleError
from .learning_data import collect_completed_learning_bars
from .intraday_shadow_scan import orderless_market_data_view, run_intraday_shadow_scan
from .learning_runner import (
    LearningCancellation,
    LearningProgress,
    LearningRunResult,
    run_learning_only,
)
from .operating_state import OperatingState, OperatingStateStore, StateTransitionError
from .market_hours import EASTERN, latest_completed_market_date
from .quant_data.resources import application_data_root
from .quant_data.symbol_selector import StrategyResolutionBlock, resolve_strategy
from .quant_data.universe_snapshot import load_default_universe
from .unattended_policy import is_recoverable_preorder_failure


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
        try:
            current = self.operating_store.load()
            market_date = now.astimezone(EASTERN).date().isoformat()
            completed_market_date = latest_completed_market_date(now)
            transition = self.operating_coordinator.advance(
                now,
                self._operating_health(),
                reconciliation_complete=(
                    current.last_reconciled_market_date == market_date
                ),
                new_data_available=bool(
                    completed_market_date
                    and current.last_learning_market_date != completed_market_date
                ),
            )
        except PreOrderCycleError as exc:
            self._enter_safe_halt(exc.reason, now)
            return []
        except StateTransitionError as exc:
            self._handle_operating_failure(exc.reason, now)
            return []
        except Exception:  # noqa: BROAD_EXCEPT_OK
            self._handle_operating_failure("operating_preflight_failed", now)
            return []
        if current.state is not transition.state:
            self.runtime_recorder.transition(
                now,
                transition.state.value,
                transition.reason,
            )
        if transition.state is not OperatingState.INTRADAY_SHADOW_SCAN:
            self.last_shadow_scan = None
        if transition.state is OperatingState.INTRADAY_SHADOW_SCAN:
            try:
                engine = self._create_engine()
                self.last_shadow_scan = run_intraday_shadow_scan(
                    self.config,
                    orderless_market_data_view(engine.market_data),
                    now,
                    application_data_root() / "runtime" / "intraday_shadow_scan.json",
                )
            except Exception:  # noqa: BROAD_EXCEPT_OK
                self._enter_safe_halt("market_data_unavailable", now)
                return []
        if transition.state is OperatingState.LIVE_TRADING:
            try:
                return self.run_auto_cycle(force=force)
            except PreOrderCycleError as exc:
                self._enter_safe_halt(exc.reason, now)
                return []
        if transition.state is OperatingState.POST_MARKET_RECONCILIATION:
            try:
                self.refresh_portfolio()
            except Exception:  # noqa: BROAD_EXCEPT_OK
                self._enter_safe_halt("account_state_unavailable", now)
                return []
            reconciled = self.operating_store.load()
            self.operating_store.save(
                replace(
                    reconciled,
                    last_reconciled_market_date=market_date,
                )
            )
        if transition.state is OperatingState.OFF_HOURS_LEARNING:
            try:
                result = self._execute_learning(
                    LearningCancellation(self._record_learning_progress)
                )
            except (BrokerRequestError, OSError):
                self._enter_safe_halt("market_data_unavailable", now)
                return []
            self._record_completed_learning(result, completed_market_date)
        if transition.state in (
            OperatingState.SAFE_HALT,
            OperatingState.EMERGENCY_STOP,
        ):
            self._handle_operating_failure(transition.reason, now)
        with self._lock:
            if self.last_error == "market_data_unavailable" and transition.state in (
                OperatingState.OFF_HOURS_LEARNING,
                OperatingState.INTRADAY_SHADOW_SCAN,
            ):
                self.last_error = None
            self.last_run_at = now
            self.next_run_at = now + timedelta(seconds=self.interval_seconds)
        return []

    def _enter_safe_halt(self, reason: str, now: datetime) -> None:
        halted = self.operating_coordinator.safe_halt(reason, now)
        self.runtime_recorder.transition(now, halted.state.value, halted.reason)
        self._handle_operating_failure(halted.reason, now)

    def _handle_operating_failure(
        self,
        reason: str,
        now: datetime,
    ) -> None:
        recoverable = (
            self.trading_settings.unattended_operation_enabled
            and is_recoverable_preorder_failure(reason)
        )
        with self._lock:
            if not recoverable:
                self.state = "paused"
            self.last_error = reason
            self.next_run_at = (
                now + timedelta(seconds=self.interval_seconds)
                if recoverable
                else None
            )

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
            result = self._execute_learning(control)
            self._record_completed_learning(
                result,
                latest_completed_market_date(self._clock()),
            )
            return result
        finally:
            safe_state = (
                previous_operating_state.state
                if previous_operating_state.state
                in (OperatingState.SAFE_HALT, OperatingState.EMERGENCY_STOP)
                else OperatingState.IDLE
            )
            current_state = self.operating_store.load()
            self.operating_store.save(
                replace(
                    current_state,
                    state=safe_state,
                    entered_at=self._clock().astimezone(timezone.utc),
                    active_job_key=None,
                )
            )
            with self._lock:
                self._learning_cancellation = None

    def _record_completed_learning(
        self,
        result: LearningRunResult,
        completed_market_date: str,
    ) -> None:
        self.runtime_recorder.learning(self._clock(), result, completed_market_date)
        if result.status != "completed" or not completed_market_date:
            return
        learned = self.operating_store.load()
        self.operating_store.save(
            replace(
                learned,
                last_learning_market_date=completed_market_date,
            )
        )

    def cancel_learning(self) -> None:
        with self._lock:
            cancellation = self._learning_cancellation
        if cancellation is not None:
            cancellation.cancel()

    def _record_learning_progress(self, progress: LearningProgress) -> None:
        with self._lock:
            self.last_learning_progress = progress

    def record_unattended_start(self) -> None:
        self.runtime_recorder.unattended_start(self._clock(), self.state)

    def _execute_learning(
        self,
        control: LearningCancellation,
    ) -> LearningRunResult:
        engine = self._create_engine()
        if isinstance(engine.market_data, DryRunMarketData):
            return run_learning_only(bars_by_symbol={}, cancellation=control)
        learning_config = self.config
        if (
            self.trading_settings.auto_symbol_selection_enabled
            and not learning_config.symbols
        ):
            learning_config = replace(
                learning_config,
                symbols=[
                    item.symbol for item in load_default_universe().symbols
                ],
            )
        bars = collect_completed_learning_bars(
            learning_config,
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
