from __future__ import annotations

from dataclasses import replace

from .automatic_order_context import automatic_order_context
from .automatic_order_types import AutomaticBlockRequest
from .automatic_risk import CycleReservationLedger
from .broker_response import broker_response_submitted
from .brokers.common import BrokerRequestError
from .config_manager import ai_features_enabled, record_submitted_order
from .daily_buy_objective import DAILY_MINIMUM_RISK_PCT, daily_minimum_decision
from .engine_automatic_cycle import EngineAutomaticCycleMixin
from .engine_errors import PreOrderCycleError
from .entry_pricing import price_entry_decision
from .exit_diagnostics import exit_diagnostics
from .models import AccountSnapshot, Bar, Position, TradeDecision
from .risk import RiskManager
from .trading_agents import apply_trading_agents_policy


class EngineCycleMixin(EngineAutomaticCycleMixin):
    def run_once(self) -> list[dict]:
        """Load data, score each symbol, and submit allowed orders."""

        if (
            self.trading_settings is not None
            and self.trading_settings.auto_symbol_selection_enabled
        ):
            return self._run_automatic_symbol_cycle()
        try:
            account = self._load_account()
            positions = self._load_positions()
        except (BrokerRequestError, OSError) as exc:
            raise PreOrderCycleError("account_state_unavailable") from exc
        base_data_symbols = self._data_symbols()
        data_symbols = [
            *base_data_symbols,
            *(symbol for symbol in positions if symbol not in base_data_symbols),
        ]
        try:
            bars_by_symbol = self._load_recent_bars(data_symbols)
        except (BrokerRequestError, OSError) as exc:
            raise PreOrderCycleError("market_data_unavailable") from exc
        self.trading_session_state.observe_portfolio(positions, self._clock())
        protective_symbols = self._protective_exit_symbols(
            bars_by_symbol,
            positions,
        )
        if protective_symbols:
            return self._run_rule_decision_cycle(
                bars_by_symbol,
                account,
                positions,
                symbols=protective_symbols,
            )
        if self.trading_settings is not None and ai_features_enabled(self.trading_settings):
            ai_result = self._run_ai_decision_cycle(bars_by_symbol, account, positions)
            if ai_result is not None:
                return [ai_result]

        return self._run_rule_decision_cycle(bars_by_symbol, account, positions)

    def _protective_exit_symbols(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        positions: dict[str, Position],
    ) -> list[str]:
        return [
            symbol
            for symbol, position in positions.items()
            if self.strategy.protective_exit(
                symbol,
                bars_by_symbol.get(symbol, []),
                self.trading_session_state.position_with_high_water(symbol, position),
            )
            is not None
        ]

    def _run_rule_decision_cycle(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        account: AccountSnapshot,
        positions: dict[str, Position],
        symbols: list[str] | None = None,
        entry_symbols: set[str] | None = None,
        automatic_risk_limits=None,
        authorization_purpose: str = "automatic",
        max_daily_order_count: int | None = None,
        daily_minimum_symbol: str = "",
        entry_prices: dict[str, float] | None = None,
    ) -> list[dict]:
        """Run the existing rule-based cycle unchanged."""

        results: list[dict] = []

        reservations = CycleReservationLedger()
        for symbol in self.config.symbols if symbols is None else symbols:
            bars = bars_by_symbol.get(symbol, [])
            position = reservations.adjusted_position(symbol, positions.get(symbol))
            self.trading_session_state.observe_position(symbol, position, self._clock())
            position = self.trading_session_state.position_with_high_water(
                symbol,
                position,
            )
            protective_decision = self.strategy.protective_exit(symbol, bars, position)
            decision = protective_decision or self.strategy.decide(symbol, bars, position)
            decision = self._time_based_sell_decision(symbol, decision, position)
            decision = daily_minimum_decision(
                self.strategy, decision, bars, position, due=symbol == daily_minimum_symbol,
            )
            if symbol == daily_minimum_symbol and decision.action == "buy":
                decision = replace(
                    decision,
                    reasons=list(dict.fromkeys([*decision.reasons, "daily_minimum_best_affordable"])),
                )
            trading_agents_advice = None
            if protective_decision is None:
                trading_agents_advice = self._trading_agents_advice(symbol)
                decision = apply_trading_agents_policy(
                    decision,
                    trading_agents_advice,
                    self.config.trading_agents,
                )
            decision = price_entry_decision(
                decision, (entry_prices or {}).get(symbol), self.config.strategy.stop_loss_pct,
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
            order_account, buying_power_check = account, None
            if decision.action == "buy":
                order_account, buying_power_check = self._account_for_order(
                    account,
                    symbol,
                    decision.latest_price,
                )
            order_account = reservations.adjusted_account(order_account)
            risk_manager = self.risk_manager
            if symbol == daily_minimum_symbol:
                risk_manager = RiskManager(replace(
                    risk_manager.config, risk_per_trade_pct=DAILY_MINIMUM_RISK_PCT,
                ))
            order = risk_manager.build_order(
                decision,
                order_account,
                position,
                decision.latest_price,
            )

            response = None
            if order is not None:
                automatic_context = automatic_order_context(
                    self,
                    bars,
                ) if entry_symbols is not None else None
                if automatic_context is not None:
                    automatic_context = replace(
                        automatic_context,
                        authorization_purpose=authorization_purpose,
                        max_daily_order_count=(
                            max_daily_order_count
                            if max_daily_order_count is not None
                            else automatic_context.max_daily_order_count
                        ),
                    )
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
                    response = self._submit_or_block_order(
                        order, automatic_context, decision.latest_price,
                        daily_minimum_buy=(symbol == daily_minimum_symbol and order.side == "buy"),
                    )
                    record_submitted_order(
                        order,
                        response,
                        self.trading_session_state,
                        self._clock(),
                    )
                    submitted = broker_response_submitted(response) or (
                        response.get("broker_submitted") is True
                    )
                    if order.side == "buy" and (
                        submitted or self.config.mode == "dry_run"
                    ):
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
                    "exit_diagnostics": exit_diagnostics(self.strategy, bars, position),
                    "evaluation_timestamp": self._clock().isoformat(),
                    "indicator_timeframe": self.config.timeframe,
                }
            )
            if isinstance(response, dict) and response.get("terminal") is True:
                break
        return results
