from __future__ import annotations

from .automatic_selection import AutomaticSelectionRequest
from .automatic_selection_production import prepare_production_automatic_selection
from .brokers.common import BrokerRequestError
from .engine_errors import PreOrderCycleError
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
        if self.config.mode == "live":
            cycle_reason = self.automatic_order_guard.start_cycle(self._clock())
            if cycle_reason:
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
        if selection.report.status == "blocked":
            return []
        try:
            account = self._load_account()
            positions = self._load_positions()
        except (BrokerRequestError, OSError) as exc:
            raise PreOrderCycleError("account_state_unavailable") from exc
        selected = list(selection.report.selected_symbols)
        symbols = [*selected, *(symbol for symbol in positions if symbol not in selected)]
        bars_by_symbol = dict(selection.bars_by_symbol)
        missing = [symbol for symbol in positions if symbol not in bars_by_symbol]
        if missing:
            try:
                bars_by_symbol.update(self._load_recent_bars(missing))
            except (BrokerRequestError, OSError) as exc:
                raise PreOrderCycleError("market_data_unavailable") from exc
        results = self._run_rule_decision_cycle(
            bars_by_symbol,
            account,
            positions,
            symbols=symbols,
            entry_symbols=set(selected),
            automatic_risk_limits=selection.risk_limits,
        )
        for item in results:
            item["selection_report"] = selection.report
        return results
