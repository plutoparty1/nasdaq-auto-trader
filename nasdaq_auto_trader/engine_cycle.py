from __future__ import annotations

from .automatic_selection import AutomaticSelectionRequest
from .automatic_selection_production import prepare_production_automatic_selection
from .automatic_order_guard import AutomaticOrderContext
from .automatic_order_types import AutomaticBlockRequest
from .automatic_risk import CycleReservationLedger
from .broker_response import broker_response_submitted
from .config_manager import ai_features_enabled, record_submitted_order
from .models import AccountSnapshot, Bar, OrderRequest, Position, TradeDecision
from .live_authorization import risk_config_digest
from .automatic_risk_config import learned_risk_config_digest
from .quant_data.symbol_selector import blocked_selection_report_without_snapshot
from .session_state_persistence import save_session_state
from .trading_agents import apply_trading_agents_policy


class EngineCycleMixin:
    def run_once(self) -> list[dict]:
        """Load data, score each symbol, and submit allowed orders."""

        if (
            self.trading_settings is not None
            and self.trading_settings.auto_symbol_selection_enabled
        ):
            return self._run_automatic_symbol_cycle()
        bars_by_symbol = self._load_recent_bars(self._data_symbols())
        account = self._load_account()
        positions = self._load_positions()
        if self.trading_settings is not None and ai_features_enabled(self.trading_settings):
            ai_result = self._run_ai_decision_cycle(bars_by_symbol, account, positions)
            if ai_result is not None:
                return [ai_result]

        return self._run_rule_decision_cycle(bars_by_symbol, account, positions)

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
        selection = prepare_production_automatic_selection(
            AutomaticSelectionRequest(
                self.config,
                self.market_data,
                self.strategy_artifact_paths,
                self._clock(),
            )
        )
        self.last_selection_report = selection.report
        self.automatic_risk_limits = selection.risk_limits
        if selection.report.status == "blocked":
            return []
        account = self._load_account()
        positions = self._load_positions()
        selected = list(selection.report.selected_symbols)
        symbols = [*selected, *(symbol for symbol in positions if symbol not in selected)]
        bars_by_symbol = dict(selection.bars_by_symbol)
        missing = [symbol for symbol in positions if symbol not in bars_by_symbol]
        if missing:
            bars_by_symbol.update(self._load_recent_bars(missing))
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

    def _run_rule_decision_cycle(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        account: AccountSnapshot,
        positions: dict[str, Position],
        symbols: list[str] | None = None,
        entry_symbols: set[str] | None = None,
        automatic_risk_limits=None,
    ) -> list[dict]:
        """Run the existing rule-based cycle unchanged."""

        results: list[dict] = []

        reservations = CycleReservationLedger()
        for symbol in self.config.symbols if symbols is None else symbols:
            bars = bars_by_symbol.get(symbol, [])
            position = reservations.adjusted_position(symbol, positions.get(symbol))
            if self.trading_settings is not None:
                self.trading_session_state.observe_position(symbol, position, self._clock())
            decision = self.strategy.decide(symbol, bars, position)
            decision = self._time_based_sell_decision(symbol, decision, position)
            trading_agents_advice = self._trading_agents_advice(symbol)
            decision = apply_trading_agents_policy(
                decision,
                trading_agents_advice,
                self.config.trading_agents,
            )
            if (
                entry_symbols is not None
                and symbol not in entry_symbols
                and decision.action == "buy"
            ):
                decision = TradeDecision(
                    symbol,
                    "hold",
                    decision.score,
                    decision.latest_price,
                    [*decision.reasons, "not_selected_for_entry"],
                    decision.risk_per_share,
                )
            order_account, buying_power_check = self._account_for_order(
                account,
                symbol,
                decision.latest_price,
            )
            order_account = reservations.adjusted_account(order_account)
            order = self.risk_manager.build_order(
                decision,
                order_account,
                position,
                decision.latest_price,
            )

            response = None
            if order is not None:
                automatic_context = _automatic_order_context(
                    self,
                    bars,
                ) if entry_symbols is not None else None
                response = None
                response = self._settings_block_response(
                    order,
                    order_account,
                    position,
                )
                if response is None and automatic_risk_limits is not None:
                    order, risk_reason = reservations.apply_limits(
                        order,
                        decision,
                        decision.latest_price,
                        account,
                        positions,
                        automatic_risk_limits,
                        self.trading_session_state.buy_count
                        + self.trading_session_state.sell_count,
                        self.trading_session_state.starting_equity,
                    )
                    if risk_reason:
                        if risk_reason == "learned_daily_loss_limit_reached":
                            self.trading_session_state.daily_loss_breached = True
                        response = {"status": "blocked", "reason": risk_reason}
                if (
                    response is not None
                    and automatic_context is not None
                    and self.config.mode == "live"
                ):
                    self.automatic_order_guard.record_block(
                        AutomaticBlockRequest(
                            automatic_context,
                            order,
                            str(response.get("reason", "settings_guard_blocked")),
                        )
                    )
                if response is None:
                    response = self._submit_or_block_order(order, automatic_context)
                    record_submitted_order(
                        order,
                        response,
                        self.trading_session_state,
                        self._clock(),
                    )
                    submitted = broker_response_submitted(response) or (
                        response.get("broker_submitted") is True
                    )
                    if order.side == "buy" and submitted:
                        reservations.reserve(order, decision.latest_price)

            results.append(
                {
                    "symbol": symbol,
                    "decision": decision,
                    "order": order,
                    "response": response,
                    "account": order_account,
                    "buying_power_check": buying_power_check,
                    "trading_agents": trading_agents_advice,
                }
            )
            if isinstance(response, dict) and response.get("terminal") is True:
                break
        return results


def _automatic_order_context(
    engine: EngineCycleMixin,
    bars: list[Bar],
) -> AutomaticOrderContext | None:
    report = engine.last_selection_report
    settings = engine.trading_settings
    if report is None or settings is None:
        return None
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
        signal_timestamp=bars[-1].timestamp if bars else "",
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
