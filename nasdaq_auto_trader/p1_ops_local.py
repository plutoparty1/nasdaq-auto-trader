"""Operating local account; frozen research ledger is never opened or advanced."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import final

from .entry_comparison import JsonValue
from .p1_ops_checkpoint import write_checkpoint
from .p1_paper_inputs import PaperReceipt
from .p1_paper_protocol import SYMBOLS, PaperProtocol, utc
from .p1_paper_session import new_account_state, restore_accounts
from .p1_paper_store import read_checkpoint


@final
class LocalOperatingSession:
    def __init__(self, directory: Path, protocol: PaperProtocol) -> None:
        self.directory, self.protocol = directory, protocol
        directory.mkdir(parents=True, exist_ok=True)
        if (directory / 'CURRENT').exists():
            self.pointer, self.state = read_checkpoint(directory)
            if self.state.get('kind') != 'p1-ops-local-v1':
                raise ValueError('operating_account_identity_mismatch')
        else:
            if any(directory.glob('checkpoint-*.json')):
                raise ValueError('operating_checkpoint_pointer_missing')
            from datetime import UTC
            self.state = new_account_state(protocol, datetime.now(UTC))
            self.state.update(kind='p1-ops-local-v1', message='초기 자료 대기; 과거 보유 없음')
            self.pointer = write_checkpoint(directory, self.state, None)
        self.accounts = restore_accounts(self.state, protocol)

    def consume(self, receipt: PaperReceipt, now: datetime, *, entries_allowed: bool) -> None:
        before = deepcopy(self.state)
        try:
            self._consume(receipt, now, entries_allowed=entries_allowed)
        except Exception:
            self.state = before
            self.accounts = restore_accounts(before, self.protocol)
            raise

    def _consume(self, receipt: PaperReceipt, now: datetime, *, entries_allowed: bool) -> None:
        sessions = self.protocol.sessions
        completed = [i for i, session in enumerate(sessions) if utc(session.close_at) <= now]
        if not completed or completed[-1] + 1 >= len(sessions):
            raise ValueError('operating_calendar_out_of_range')
        index = completed[-1]
        current, following = sessions[index:index + 2]
        if self.state.get('last_session') == current.day:
            return
        reasons = list(receipt.failures)
        bars = [bar for history in receipt.bars.values() for bar in history
                if bar.timestamp == current.close_at]
        if {bar.symbol for bar in bars} != set(SYMBOLS):
            reasons.append('missing_current_cohort_data')
        if now >= utc(following.open_at):
            reasons.append('stale_close_after_next_open')
        if receipt.split_dates:
            reasons.append('corporate_action_requires_review')
        for account in self.accounts.values():
            for symbol, history in receipt.bars.items():
                known = {bar.timestamp: bar for bar in account.histories.get(symbol, [])}
                if any(bar.timestamp in known and bar != known[bar.timestamp] for bar in history):
                    raise ValueError('observed_bar_revision_requires_review')
        if not bars:
            self.state['message'] = '; '.join(reasons)
            self.save()
            return
        previous = self.state.get('last_session')
        if previous is None:
            history = {symbol: [bar for bar in receipt.bars.get(symbol, [])
                                if bar.timestamp <= current.close_at][-64:] for symbol in SYMBOLS}
            if any(len(values) < 64 for values in history.values()) or reasons:
                self.state['message'] = '; '.join(reasons + ['warmup_not_ready'])
                self.save()
                return
            for account in self.accounts.values():
                account.warmup(history)
            self.state['message'] = '과거 자료는 지표 준비에만 사용; 다음 완성 일봉부터 판단'
            self.state['initial_fx'] = receipt.fx[-1].usdkrw if receipt.fx else None
            self.state['initial_fx_as_of'] = receipt.fx[-1].timestamp if receipt.fx else None
        else:
            prior = next(i for i, session in enumerate(sessions) if session.day == previous)
            missed = index > prior + 1
            if missed:
                reasons.append('missed_sessions_not_replayed:' + str(index - prior - 1))
            for account in self.accounts.values():
                for symbol, pending in tuple(account.book.pending.items()):
                    if symbol not in {bar.symbol for bar in bars}:
                        account.book.reject(pending, current.close_at, 'missing_session_expired')
                        del account.book.pending[symbol]
                        del account.actual_decisions[symbol]
                additional = {symbol: [bar for bar in receipt.bars.get(symbol, [])
                                       if account.histories[symbol][-1].timestamp < bar.timestamp < current.close_at]
                              for symbol in SYMBOLS}
                if any(additional.values()):
                    account.observe_missed_history(additional)
                account.advance(bars, observed_at=now.isoformat(), session_open_at=current.open_at,
                                entries_allowed=entries_allowed and not reasons, missed_session=missed)
            self.state['message'] = '; '.join(reasons) or '완성 일봉 처리; 체결은 다음 봉 모형의 로컬 모의 체결'
        self.state['last_session'] = current.day
        self.state['updated_at'] = now.isoformat()
        self.state['receipt_sha256'] = receipt.sha256
        self.state['received_at'] = dict(receipt.received_at)
        self.state['event_close_at'] = current.close_at
        self.save()

    def save(self) -> None:
        self.state['accounts'] = {name: account.export_state() for name, account in self.accounts.items()}
        self.pointer = write_checkpoint(self.directory, self.state, self.pointer)

    def status(self) -> dict[str, JsonValue]:
        base = self.accounts['base']
        account = base.book.account()
        scenarios: dict[str, JsonValue] = {}
        for name, book in self.accounts.items():
            scenarios[name] = {'equity': book.book.account().equity,
                               'fills': len(book.book.trades), 'pending': len(book.book.pending)}
        last_reasons: list[JsonValue] = [record.first_reason for record in base.risk.records[-3:]]
        return {'cash': account.cash, 'equity': account.equity,
                'positions': [asdict(position) for position in base.book.positions.values()],
                'pending': len(base.book.pending), 'scenarios': scenarios,
                'completed_sessions': len(base.equity_curve),
                'message': self.state.get('message', ''), 'no_buy_reasons': last_reasons,
                'updated_at': self.state.get('updated_at'), 'last_session': self.state.get('last_session'),
                'initial_fx': self.state.get('initial_fx'), 'fill_kind': 'LOCAL_SIMULATED',
                'independent_evaluation': 'separate_research_ledger_unchanged'}

    def close(self) -> None:
        self.save()
