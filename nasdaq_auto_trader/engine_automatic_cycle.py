from __future__ import annotations

from .automatic_selection import AutomaticSelectionRequest
from .automatic_selection_production import prepare_production_automatic_selection
from .brokers.common import BrokerRequestError
from .engine_errors import PreOrderCycleError
from .live_authorization import LiveAuthorizationRequest, create_live_authorization
from .quant_data.symbol_selector import blocked_selection_report_without_snapshot
from .session_state_persistence import save_session_state


class EngineAutomaticCycleMixin:
    def _run_automatic_symbol_cycle(self) -> list[dict]:
        try:
            return self._execute_automatic_symbol_cycle()
        finally:
            if self._persist_automatic_session:
                save_session_state(
                    self.automatic_order_guard.session_store,
                    self.trading_session_state,
                )

    def _execute_automatic_symbol_cycle(self) -> list[dict]:
        cycle_reason = ""
        if self.config.mode == "live":
            cycle_reason = self.automatic_order_guard.start_cycle(self._clock())
            if cycle_reason and not (
                cycle_reason == "live_authorization_required"
                and self._automatic_session_authorization_allowed()
            ):
                self.last_selection_report = blocked_selection_report_without_snapshot(
                    cycle_reason
                )
                return []
        if self.automatic_preflight_reason:
            self.last_selection_report = blocked_selection_report_without_snapshot(
                self.automatic_preflight_reason
            )
            return []
        try:
            account = self._load_account()
            positions = self._load_positions()
        except (BrokerRequestError, OSError) as exc:
            raise PreOrderCycleError("account_state_unavailable") from exc
        self.trading_session_state.observe_portfolio(positions, self._clock())
        held_bars = {}
        if positions:
            try:
                held_bars = self._load_recent_bars(list(positions))
            except (BrokerRequestError, OSError) as exc:
                raise PreOrderCycleError("market_data_unavailable") from exc
        protective_symbols = self._protective_exit_symbols(held_bars, positions)
        try:
            selection = prepare_production_automatic_selection(
                AutomaticSelectionRequest(
                    self.config,
                    self.market_data,
                    self.strategy_artifact_paths,
                    self._clock(),
                )
            )
        except (BrokerRequestError, OSError) as exc:
            raise PreOrderCycleError("market_data_unavailable") from exc
        self.last_selection_report = selection.report
        self.automatic_risk_limits = selection.risk_limits
        if protective_symbols:
            if (
                self.config.mode == "live"
                and self._automatic_session_authorization_allowed()
            ):
                authorization_reason = self._ensure_automatic_authorization()
                if authorization_reason:
                    self.last_selection_report = blocked_selection_report_without_snapshot(
                        authorization_reason
                    )
                    return []
                cycle_reason = ""
            if cycle_reason:
                self.last_selection_report = blocked_selection_report_without_snapshot(
                    cycle_reason
                )
                return []
            return self._run_rule_decision_cycle(
                held_bars,
                account,
                positions,
                symbols=protective_symbols,
                entry_symbols=set(),
                authorization_purpose="automatic",
                max_daily_order_count=0,
            )
        if selection.report.status == "blocked":
            return []
        selected = list(selection.report.selected_symbols)
        symbols = [*positions, *(symbol for symbol in selected if symbol not in positions)]
        if not symbols:
            return []
        bars_by_symbol = {**held_bars, **selection.bars_by_symbol}
        missing = [symbol for symbol in positions if symbol not in bars_by_symbol]
        if missing:
            try:
                bars_by_symbol.update(self._load_recent_bars(missing))
            except (BrokerRequestError, OSError) as exc:
                raise PreOrderCycleError("market_data_unavailable") from exc
        if (
            self.config.mode == "live"
            and self._automatic_session_authorization_allowed()
        ):
            authorization_reason = self._ensure_automatic_authorization()
            if authorization_reason:
                self.last_selection_report = blocked_selection_report_without_snapshot(
                    authorization_reason
                )
                return []
            cycle_reason = ""
        results = []
        if not cycle_reason:
            results = self._run_rule_decision_cycle(
                bars_by_symbol,
                account,
                positions,
                symbols=symbols,
                entry_symbols=set(selected),
                automatic_risk_limits=selection.risk_limits,
                authorization_purpose="automatic",
                max_daily_order_count=0,
            )
        for item in results:
            item["selection_report"] = selection.report
        return results

    def _ensure_automatic_authorization(self) -> str:
        return self.automatic_order_guard.ensure_live_authorization(
            create_live_authorization(
                LiveAuthorizationRequest(
                    self.config,
                    self.strategy_artifact_paths,
                    self._clock(),
                    max_attempts=0,
                    purpose="automatic",
                )
            )
        )

    def _automatic_session_authorization_allowed(self) -> bool:
        settings = self.trading_settings
        return bool(
            settings is not None
            and settings.automatic_session_authorization_enabled
            and settings.unattended_operation_enabled
            and settings.unattended_live_trading_enabled
            and self.config.broker == "kis"
        )
