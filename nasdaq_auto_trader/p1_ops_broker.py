"""P1 daily signals with broker-confirmed fills; callers must hold the operating lock and lease."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import final

from .brokers.common import BrokerOrderError, BrokerOrderRejected, BrokerRequestError
from .entry_comparison import JsonValue
from .models import Bar, OrderRequest
from .p1_ops_broker_models import (
    ACTIVE,
    UNCERTAIN,
    OperatingBroker,
    OperatingError,
    OrderState,
)
from .p1_ops_broker_planning import plan_completed, quantity_for, validate_completed
from .p1_ops_broker_reconcile import reconcile
from .p1_ops_broker_store import OperatingStore
from .p1_ops_kis import P1SubmissionBlocked
from .p1_paper_models import timestamp
from .p1_paper_protocol import STARTING_USD, PaperProtocol, PaperSession


@final
class BrokerOperatingSession:
    def __init__(self, directory: Path, protocol: PaperProtocol, broker: OperatingBroker,
                 mode: str = 'kis_paper', *,
                 authorize_live: Callable[[OrderRequest], bool] | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        if mode == 'kis_live':
            raise OperatingError('p1_live_authorization_unavailable')
        if mode not in ('kis_paper', 'kis_live'):
            raise OperatingError('unsupported_broker_operating_mode')
        if broker.credentials.paper != (mode == 'kis_paper') or not broker.account_fingerprint:
            raise OperatingError('broker_mode_or_identity_mismatch')
        self.directory, self.protocol, self.broker, self.mode = directory, protocol, broker, mode
        self.identity, self.authorize_live = broker.account_fingerprint, authorize_live
        self.clock = clock
        self.store = OperatingStore(directory, protocol, mode, self.identity)
        self.closed = False
        if self.store.checkpoint is None:
            self.store.save()

    def _run(self, action: Callable[[], None]) -> None:
        if self.closed:
            raise OperatingError('operating_session_closed')
        if (self.broker.account_fingerprint != self.identity
                or self.broker.credentials.paper != (self.mode == 'kis_paper')):
            raise OperatingError('broker_mode_or_identity_changed')
        finished = False
        try:
            action()
            self.store.save()
            finished = True
        finally:
            if not finished:
                self.store = OperatingStore(self.directory, self.protocol, self.mode, self.identity)

    def evaluate_completed(self, bars_by_symbol: dict[str, list[Bar]], observed_at: datetime,
                           signal_session: PaperSession, next_session: PaperSession,
                           entries_allowed: bool) -> dict[str, JsonValue]:
        def evaluate() -> None:
            if self.store.state.observed_at and observed_at < timestamp(self.store.state.observed_at):
                raise OperatingError('operating_clock_moved_backwards')
            validate_completed(self.store, bars_by_symbol, observed_at, signal_session, next_session)
            _ = reconcile(self.store, self.broker, observed_at)
            plan_completed(self.store, bars_by_symbol, observed_at, signal_session, next_session, entries_allowed)

        self._run(evaluate)
        return self.status()

    def tick(self, now: datetime, entries_allowed: bool) -> dict[str, JsonValue]:
        if now.tzinfo is None:
            raise OperatingError('operating_clock_timezone_required')

        def operate() -> None:
            if self.store.state.observed_at and now < timestamp(self.store.state.observed_at):
                raise OperatingError('operating_clock_moved_backwards')
            _ = reconcile(self.store, self.broker, now)
            self.store.save()
            for key in tuple(self.store.state.intents):
                self._submit_plan(key, now, entries_allowed)

        self._run(operate)
        return self.status()

    def _submit_plan(self, key: str, now: datetime, entries_allowed: bool) -> None:
        state = self.store.state
        intent = state.intents[key]
        if intent.state != OrderState.PLANNED or now < timestamp(intent.open_at):
            return
        if (now >= timestamp(intent.close_at) or
                (intent.side == 'buy' and now > timestamp(intent.open_at) + timedelta(minutes=5))):
            state.intents[key] = replace(intent, state=OrderState.EXPIRED, reason='missed_submission_window')
            return
        account, positions, prior_ids = reconcile(self.store, self.broker, now)
        if (intent.side == 'buy' and (state.blockers or not entries_allowed or state.day_halted)
                or intent.side == 'sell' and intent.symbol in state.protection_blockers):
            return
        current = positions.get(intent.symbol)
        if intent.side == 'buy':
            if current is not None or intent.symbol in state.holdings:
                state.intents[key] = replace(intent, state=OrderState.BLOCKED, reason='existing_holding')
                return
            power = self.broker.get_overseas_buying_power(intent.symbol, intent.limit_price)
            qty = quantity_for(self.store, intent, account, power)
        else:
            held = state.holdings.get(intent.symbol)
            qty = 0 if held is None or current is None or current.qty != held.qty else held.qty
        if qty <= 0:
            state.intents[key] = replace(intent, state=OrderState.BLOCKED, reason='fresh_sizing_or_ownership_gate')
            return
        intent = replace(intent, qty=qty)
        request = intent.request()
        if self.mode == 'kis_live' and (self.authorize_live is None or not self.authorize_live(request)):
            state.intents[key] = replace(intent, state=OrderState.BLOCKED, reason='live_authorization_required')
            return
        prepared_at = self.clock()
        if prepared_at.tzinfo is None:
            raise OperatingError('operating_clock_timezone_required')
        intent = replace(intent, state=OrderState.SUBMITTING, submitted_at=prepared_at.isoformat(),
                         cash_before=account.cash, qty_before=current.qty if current else 0,
                         prior_order_ids=prior_ids)
        state.intents[key] = intent
        self.store.save()
        submit_now = self.clock()
        if (submit_now.tzinfo is None or submit_now < timestamp(intent.open_at)
                or submit_now >= timestamp(intent.close_at)
                or (intent.side == 'buy' and submit_now > timestamp(intent.open_at) + timedelta(minutes=5))):
            state.intents[key] = replace(intent, state=OrderState.EXPIRED, submitted_at='',
                                         reason='fresh_submission_window_elapsed')
            self.store.save()
            return
        try:
            deadline = timestamp(intent.close_at)
            if intent.side == 'buy':
                deadline = min(deadline, timestamp(intent.open_at) + timedelta(minutes=5))
            self.broker.bind_submission_window(request, timestamp(intent.open_at), deadline)
            response = self.broker.submit_order(request)
        except P1SubmissionBlocked as error:
            refused = OrderState.EXPIRED if error.reason == 'submission_window_elapsed' else OrderState.BLOCKED
            state.intents[key] = replace(intent, state=refused, submitted_at='', reason=error.reason)
        except BrokerOrderRejected:
            state.intents[key] = replace(intent, state=OrderState.REJECTED, reason='broker_rejected')
        except (BrokerOrderError, BrokerRequestError, OSError, TimeoutError):
            state.intents[key] = replace(intent, state=OrderState.UNKNOWN, reason='submission_outcome_unknown')
            state.blockers = sorted({*state.blockers, 'unknown_submission'})
        else:
            output = response.get('output')
            identifier = output.get('ODNO', output.get('odno')) if isinstance(output, dict) else None
            if response.get('rt_cd') == '0' and isinstance(identifier, str) and identifier.strip():
                responded_at = self.clock()
                if responded_at.tzinfo is None or responded_at < prepared_at:
                    raise OperatingError('invalid_submission_response_clock')
                self.store.codec.strategy.register_order_accepted(intent.symbol, intent.signal_at)
                state.intents[key] = replace(intent, state=OrderState.ACCEPTED, order_id=identifier,
                                             response_at=responded_at.isoformat())
            else:
                state.intents[key] = replace(intent, state=OrderState.UNKNOWN, reason='submission_identity_missing')
                state.blockers = sorted({*state.blockers, 'unknown_submission'})
        self.store.save()

    def status(self) -> dict[str, JsonValue]:
        state = self.store.state
        positions: list[JsonValue] = [{'symbol': item.symbol, 'qty': item.qty,
            'average_price': item.average_price, 'stop_price': item.stop_price,
            'high_water_price': item.high_water_price, 'market_value': item.qty * item.mark_price}
            for item in state.holdings.values()]
        orders: list[JsonValue] = [{'symbol': item.symbol, 'side': item.side,
            'status': item.state.value, 'qty': item.qty, 'filled_qty': item.filled_qty,
            'limit_price': item.limit_price, 'signal_at': item.signal_at, 'open_at': item.open_at,
            'reason': item.reason} for item in state.intents.values()]
        blockers: list[JsonValue] = list(state.blockers)
        if any(item.state in UNCERTAIN for item in state.intents.values()) and 'unknown_submission' not in blockers:
            blockers.append('unknown_submission')
        if self.mode == 'kis_live' and self.authorize_live is None:
            blockers.append('live_authorization_required')
        no_buy_reasons: list[JsonValue] = [f'{row.symbol}: {row.final_action} / {row.reason}'
            for row in self.store.codec.strategy.records[-3:]]
        no_buy_reasons.extend(f'{item.symbol}: {item.reason}' for item in state.intents.values()
                              if item.reason)
        return {'mode': self.mode, 'execution_policy': 'next_regular_session_day_limit',
            'fill_source': 'broker_confirmed_history', 'starting_usd': STARTING_USD,
            'cash_usd': state.cash, 'equity_usd': state.equity(),
            'estimated_costs_usd': state.costs, 'costs_label': 'estimates_not_broker_reported_fees',
            'realized_pnl_usd': state.realized, 'maximum_observed_loss_usd': state.maximum_loss,
            'maximum_drawdown_usd': state.maximum_drawdown, 'daily_loss_halted': state.day_halted,
            'blockers': blockers, 'positions': positions, 'orders': orders,
            'no_buy_reasons': no_buy_reasons[-6:],
            'observed_at': state.observed_at, 'closed': self.closed,
            'pending_orders': sum(item.state in ACTIVE for item in state.intents.values())}

    def close(self) -> None:
        if not self.closed:
            self.store.save()
            self.closed = True
