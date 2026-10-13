from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from math import isfinite

from .backtest_types import BacktestResult, EquityPoint
from .experimental_exit_models import ExitPolicy
from .models import Bar
from .p1_paper_codec import decode_state, encode_state, read_json
from .p1_paper_models import (
    EntryRiskRecord,
    PaperAccountError,
    PaperFillRecord,
    PaperState,
    RiskState,
    StrategyState,
    bar_digest,
    bar_identity,
    normalized_bar,
    timestamp,
    validate_bar,
)
from .profitability_execution import ConservativeCosts
from .profitability_strategy import ProfitabilityStrategy
from .sizing_entry_execution import DynamicExecutionBook
from .sizing_entry_risk import DynamicEntryRisk
from .strategy_config import StrategyConfig


class PaperAccount:
    """Mutable offline P1 ledger; fills model session opens and never place broker orders."""

    def __init__(self, config: StrategyConfig, policy: ExitPolicy,
                 costs: ConservativeCosts, starting_cash: float) -> None:
        if not isfinite(starting_cash) or starting_cash <= 0 or costs.quantity_step != 1:
            raise PaperAccountError('positive finite starting cash and whole-share costs required')
        self.config, self.policy, self.costs, self.starting_cash = config, policy, costs, starting_cash
        self.fingerprint = sha256(dumps([asdict(config), asdict(policy), asdict(costs), starting_cash],
                                       sort_keys=True, allow_nan=False).encode()).hexdigest()
        self.strategy = ProfitabilityStrategy(config, policy)
        self.risk = DynamicEntryRisk(self.strategy, costs)
        self.book = DynamicExecutionBook(starting_cash, costs, .06, .02, self.strategy, True,
                                        max_total_position_pct=.5)
        self.risk.bind_book(self.book)
        self.histories: dict[str, list[Bar]] = {}
        self.processed: dict[str, str] = {}
        self.equity_curve: list[EquityPoint] = []
        self.actual_decisions: dict[str, str] = {}
        self.fill_records: list[PaperFillRecord] = []
        self.entry_risks: list[EntryRiskRecord] = []
        self.observed_at = ''

    def warmup(self, bars_by_symbol: dict[str, list[Bar]]) -> None:
        if self.equity_curve:
            raise PaperAccountError('warmup is only permitted before the first paper session')
        self.observe_missed_history(bars_by_symbol)

    def observe_missed_history(self, bars_by_symbol: dict[str, list[Bar]]) -> None:
        histories = {symbol: list(history) for symbol, history in self.histories.items()}
        processed = dict(self.processed)
        now = datetime.now(UTC)
        for symbol, history in bars_by_symbol.items():
            for bar in history:
                validate_bar(bar)
                bar = normalized_bar(bar)
                if bar.symbol != symbol or timestamp(bar.timestamp) > now:
                    raise PaperAccountError('warmup bars must match their symbol and be in the past')
                identity, digest = bar_identity(bar), bar_digest(bar)
                if identity in processed:
                    if processed[identity] != digest:
                        raise PaperAccountError('conflicting previously observed bar')
                    continue
                prior = histories.setdefault(symbol, [])
                if prior and timestamp(bar.timestamp) <= timestamp(prior[-1].timestamp):
                    raise PaperAccountError('warmup bars must append chronologically')
                prior.append(bar)
                processed[identity] = digest
        self.histories, self.processed = histories, processed

    def advance(self, current: list[Bar], *, observed_at: str, session_open_at: str,
                entries_allowed: bool, missed_session: bool = False) -> None:
        observed, opened = timestamp(observed_at), timestamp(session_open_at)
        if not current:
            raise PaperAccountError('a completed session requires bars')
        ordered = sorted((normalized_bar(bar)
                          for bar in current), key=lambda bar: bar.symbol)
        if len({bar.symbol for bar in ordered}) != len(ordered):
            raise PaperAccountError('duplicate symbol within session')
        if len({bar.timestamp for bar in ordered}) != 1:
            raise PaperAccountError('advance requires one completed session timestamp')
        for bar in ordered:
            validate_bar(bar)
            stamp = timestamp(bar.timestamp)
            if not opened < stamp <= observed:
                raise PaperAccountError('session open must precede completed bar and knowledge time')
            prior = self.processed.get(bar_identity(bar))
            if prior is not None and prior != bar_digest(bar):
                raise PaperAccountError('conflicting previously observed bar')
        if all(bar_identity(bar) in self.processed for bar in ordered):
            return
        if any(bar_identity(bar) in self.processed for bar in ordered):
            raise PaperAccountError('partial session retry is not permitted')
        if self.observed_at and observed < timestamp(self.observed_at):
            raise PaperAccountError('knowledge time cannot move backwards')
        latest = ordered[0].timestamp
        if self.equity_curve and timestamp(latest) <= timestamp(self.equity_curve[-1].timestamp):
            raise PaperAccountError('completed sessions must append chronologically')
        for bar in ordered:
            history = self.histories.get(bar.symbol, [])
            if history and timestamp(bar.timestamp) <= timestamp(history[-1].timestamp):
                raise PaperAccountError('bars must follow indicator history')
        if missed_session:
            for symbol, pending in tuple(self.book.pending.items()):
                self.book.reject(pending, latest, 'missed_session_expired')
                del self.book.pending[symbol]
                del self.actual_decisions[symbol]
        for bar in ordered:
            position = self.book.positions.get(bar.symbol)
            if position is not None:
                self.book.positions[bar.symbol] = replace(position, market_value=position.qty * bar.open)
        for bar in ordered:
            pending = self.book.pending.get(bar.symbol)
            if pending is None:
                continue
            decided = self.actual_decisions[bar.symbol]
            before = len(self.book.trades)
            if timestamp(decided) >= opened:
                self.book.reject(pending, latest, 'decision_not_before_session_open')
                del self.book.pending[bar.symbol]
            else:
                self.book.execute(bar)
            if bar.symbol not in self.book.pending:
                del self.actual_decisions[bar.symbol]
            for index in range(before, len(self.book.trades)):
                trade = self.book.trades[index]
                self.fill_records.append(PaperFillRecord(index, trade.symbol, trade.side,
                    trade.signal_timestamp, decided, opened.isoformat(), observed.isoformat()))
        for bar in ordered:
            self.histories.setdefault(bar.symbol, []).append(bar)
            self.processed[bar_identity(bar)] = bar_digest(bar)
            position = self.book.positions.get(bar.symbol)
            if position is not None:
                self.book.positions[bar.symbol] = replace(position, market_value=position.qty * bar.close,
                    high_water_price=max(position.high_water_price or position.avg_entry_price, bar.close))
        for bar in ordered:
            if bar.symbol in self.book.pending:
                continue
            self.risk.timestamp = bar.timestamp
            position = self.book.positions.get(bar.symbol)
            decision = self.strategy.decide(bar.symbol, self.histories[bar.symbol], position)
            if decision.action == 'buy' and decision.risk_per_share is not None:
                stop = decision.latest_price - decision.risk_per_share
                expected_cost = self.costs.fee(decision.latest_price) + self.costs.fee(stop)
                expected_cost += (decision.latest_price + stop) * self.costs.adverse_fraction
                decision = replace(decision, risk_per_share=decision.risk_per_share + expected_cost)
            if decision.action == 'buy' and (not entries_allowed or missed_session):
                decision = replace(decision, action='hold', reasons=[*decision.reasons, 'paper_entry_gate'])
            order = self.risk.build_order(decision, self.book.account(available=True), position,
                                         decision.latest_price)
            if order is None:
                continue
            self.book.submit(order, decision, bar.timestamp)
            if bar.symbol in self.book.pending:
                self.actual_decisions[bar.symbol] = observed.isoformat()
                if order.side == 'buy':
                    sizing = self.risk.sizing_records[-1]
                    self.entry_risks.append(EntryRiskRecord(bar.timestamp, bar.symbol, observed.isoformat(),
                        sizing.equity, sizing.equity * .02, sizing.planned_risk, sizing.initial_stop,
                        sizing.selected_qty, sizing.price, sizing.buy_fee, sizing.stop_sell_fee,
                        sizing.adverse_cost))
        account = self.book.account()
        self.equity_curve.append(EquityPoint(latest, account.equity, self.book.cash, account.equity - self.book.cash))
        self.observed_at = observed.isoformat()

    def result(self) -> BacktestResult:
        return BacktestResult(self.starting_cash, self.book.account().equity, tuple(self.book.trades),
            tuple(self.equity_curve), tuple(self.book.rejections), tuple(self.book.positions.values()))

    def export_state(self) -> str:
        strategy, risk, book = self.strategy, self.risk, self.book
        exit_strategy = strategy.exit_strategy
        if exit_strategy is None:
            raise PaperAccountError('P1 requires an exit policy')
        signal = StrategyState(strategy.entry_volatility, strategy.filled_stops,
            {key: value.isoformat() for key, value in strategy._completed.items()},
            strategy._filled_qty, strategy._session_qty, strategy._accepted_timestamp,
            strategy._risk_distance, strategy.records, exit_strategy.export_state(), exit_strategy.diagnostics)
        risk_state = RiskState(risk.timestamp, risk.day, risk.previous_equity, risk.day_start_equity,
            risk.day_halted, risk.records, risk.accepted_orders, risk.sizing_records)
        return encode_state(PaperState(1, self.fingerprint, self.starting_cash, book.cash,
            book.positions, book.pending, book.trades, book.rejections, book.entry_fees, book.position_risk,
            self.histories, self.processed, self.equity_curve, self.actual_decisions,
            self.fill_records, self.entry_risks, self.observed_at, signal, risk_state))

    def load_state(self, payload: str) -> None:
        state = decode_state(payload)
        if state.fingerprint != self.fingerprint or state.starting_cash != self.starting_cash:
            raise PaperAccountError('paper account profile fingerprint mismatch')
        candidate = PaperAccount(self.config, self.policy, self.costs, self.starting_cash)
        candidate.book.cash = state.cash
        candidate.book.positions, candidate.book.pending = state.positions, state.pending
        candidate.book.trades, candidate.book.rejections = state.trades, state.rejections
        candidate.book.entry_fees, candidate.book.position_risk = state.entry_fees, state.position_risk
        candidate.histories, candidate.processed = state.histories, state.processed
        candidate.equity_curve, candidate.actual_decisions = state.equity_curve, state.actual_decisions
        candidate.fill_records, candidate.entry_risks = state.fill_records, state.entry_risks
        candidate.observed_at = state.observed_at
        strategy, signal, risk, saved = candidate.strategy, state.strategy, candidate.risk, state.risk
        strategy.entry_volatility, strategy.filled_stops = signal.entry_volatility, signal.filled_stops
        strategy._completed = {key: timestamp(value) for key, value in signal.completed.items()}
        strategy._filled_qty, strategy._session_qty = signal.filled_qty, signal.session_qty
        strategy._accepted_timestamp, strategy._risk_distance = signal.accepted_timestamp, signal.risk_distance
        strategy.records = signal.records
        exit_strategy = strategy.exit_strategy
        if exit_strategy is None:
            raise PaperAccountError('P1 requires an exit policy')
        read_json(signal.exit_payload)
        exit_strategy.load_state(signal.exit_payload)
        exit_strategy.diagnostics = signal.exit_diagnostics
        risk.timestamp, risk.day = saved.timestamp, saved.day
        risk.previous_equity, risk.day_start_equity = saved.previous_equity, saved.day_start_equity
        risk.day_halted, risk.records = saved.day_halted, saved.records
        risk.accepted_orders, risk.sizing_records = saved.accepted_orders, saved.sizing_records
        self.__dict__.update(candidate.__dict__)

