"""One user-started operating loop; isolated from legacy settings and research state."""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, final

from .entry_comparison import JsonValue
from .live_canary_lease import BrokerLiveLease
from .p1_ops_checkpoint import write_checkpoint
from .p1_ops_gui_contract import OpsStatus, Position
from .p1_ops_kis import P1OperatingKISClient
from .p1_ops_local import LocalOperatingSession
from .p1_ops_process import assert_no_legacy_process
from .p1_ops_security import (
    dedicated_environment,
    live_request,
    live_review,
    paper_credentials,
)
from .p1_paper_codec import read_json
from .p1_paper_inputs import read_receipt
from .p1_paper_protocol import STARTING_USD, PaperProtocol, utc
from .p1_paper_store import read_checkpoint
from .p1_public_receipts import collect_receipt
from .quant_data.resources import application_data_root
from .single_instance import SingleInstanceGuard

if TYPE_CHECKING:
    from .p1_ops_broker import BrokerOperatingSession

VERSION = 'p1-ops-v1'


@final
class P1OperatingController:
    def __init__(self, directory: Path, protocol: PaperProtocol, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 process_check: Callable[[], None] = assert_no_legacy_process) -> None:
        self.directory, self.protocol = directory, protocol
        self.clock, self.process_check = clock, process_check
        self.mode, self.running, self.entries_paused = 'local_paper', False, False
        self.version = VERSION + '/' + protocol.sha256[:12]
        self.message = '로컬 모의 기본값; 실전 승인 없음'
        self.backend: LocalOperatingSession | BrokerOperatingSession | None = None
        self.resources = ExitStack()
        self.guard = SingleInstanceGuard(directory / '.operator.lock')
        self.last_tick: datetime | None = None
        self.next_collect = datetime.min.replace(tzinfo=UTC)
        self.next_heartbeat = self.next_collect
        self.started_at: datetime | None = None
        self.control_pointer: str | None = None
        self.control: dict[str, JsonValue] = {'schema_version': 1}
        control_dir = directory / 'control'
        if (control_dir / 'CURRENT').exists():
            self.control_pointer, self.control = read_checkpoint(control_dir)
            self.entries_paused = self.control.get('entries_paused') is True
            previous_tick = self.control.get('last_tick')
            if isinstance(previous_tick, str):
                self.last_tick = utc(previous_tick)
        elif any(control_dir.glob('checkpoint-*.json')):
            raise ValueError('operating_control_pointer_missing')

    def start(self, mode: str) -> None:
        if mode not in ('local_paper', 'kis_paper', 'live'):
            raise ValueError('invalid_operating_mode')
        if mode == 'live':
            self.message = '실전 차단: P1에 유효한 기존 전략 승인 결합과 실전 세션 승인이 없습니다.'
            raise ValueError('p1_live_strategy_approval_binding_unavailable')
        if self.running:
            if self.mode != mode:
                raise ValueError('close_operating_session_before_mode_change')
            return
        previous_version = self.control.get('operating_version')
        if previous_version is not None and previous_version != self.version:
            raise ValueError('operating_build_changed_requires_new_state_version')
        self.process_check()
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.guard.acquire():
            raise ValueError('p1_operating_session_already_running')
        try:
            self.started_at = self.clock()
            if mode == 'local_paper':
                self.backend = LocalOperatingSession(self.directory / mode, self.protocol)
            else:
                from .p1_ops_broker import BrokerOperatingSession
                credentials = paper_credentials(dedicated_environment(self.directory / 'kis-paper.env', os.environ))
                broker = P1OperatingKISClient(credentials, self.directory / '.kis-paper-token.json', clock=self.clock)
                lease_path = application_data_root() / 'live_canary' / 'broker-live-owner.lock'
                lease = self.resources.enter_context(BrokerLiveLease.acquire(
                    lease_path, broker.account_fingerprint, frozenset(('buy', 'sell'))))
                broker.bind_live_lease(lease)
                self.backend = BrokerOperatingSession(self.directory / mode, self.protocol, broker, mode=mode, clock=self.clock)
            self.mode, self.running = mode, True
            self.message = '자동 수집/일봉 판단 대기; 신규 진입 중지 상태 복원' if self.entries_paused else '자동 수집/일봉 판단 시작'
            self._save_control()
        except Exception:
            self.running, self.backend = False, None
            self.resources.close()
            self.guard.release()
            if mode == 'kis_paper':
                self.message = 'KIS 모의 시작 실패: 전용 인증/계좌/잠금 상태를 확인하세요. 실전 인증으로 대체하지 않습니다.'
            raise

    def pause_entries(self) -> None:
        self.entries_paused = True
        self.message = '신규 진입 중지; 기존 접수 주문 조회와 보유분 일봉 보호 판단 계속'
        self._save_control()

    def resume_entries(self) -> None:
        if not self.running:
            raise ValueError('operating_session_not_started')
        self.entries_paused = False
        self.message = '신규 진입 재개; 놓친 신호는 뒤늦게 매수하지 않음'
        try:
            self._save_control()
        except OSError:
            self.entries_paused = True
            raise

    def _save_control(self) -> None:
        target = self.directory / 'control'
        target.mkdir(parents=True, exist_ok=True)
        self.control.update(entries_paused=self.entries_paused, mode=self.mode, operating_version=self.version,
                            last_tick=None if self.last_tick is None else self.last_tick.isoformat())
        self.control['last_status'] = read_json(json.dumps(self.status(), ensure_ascii=False))
        self.control_pointer = write_checkpoint(target, self.control, self.control_pointer)

    def step(self) -> None:
        try:
            self._step()
        except Exception as error:
            reason = str(error)
            safe = reason if reason.isascii() and reason.replace('_', '').isalpha() else type(error).__name__
            self.message = '운영 점검 실패; 신규 주문 판단 보류: ' + safe
            self.control['last_error'] = safe
            self._save_control()
            raise

    def _step(self) -> None:
        if not self.running or self.backend is None:
            return
        now = self.clock()
        if now.tzinfo is None or (self.last_tick is not None and now < self.last_tick):
            self.entries_paused = True
            raise ValueError('operating_clock_moved_backwards')
        gap_seconds = 0 if self.last_tick is None else (now - self.last_tick).total_seconds()
        gap = gap_seconds > 120
        self.last_tick = now
        if gap:
            self.control['last_execution_gap_seconds'] = gap_seconds
            self.control['last_execution_gap_at'] = now.isoformat()
            self.message = '실행 공백 감지; 놓친 진입은 복구 주문하지 않음'
        if now >= self.next_heartbeat:
            self._save_control()
            self.next_heartbeat = now + timedelta(minutes=1)
        self.process_check()
        if not isinstance(self.backend, LocalOperatingSession):
            _ = self.backend.tick(now=now, entries_allowed=not self.entries_paused)
        sessions = self.protocol.sessions
        completed = [i for i, session in enumerate(sessions) if utc(session.close_at) + timedelta(minutes=5) <= now]
        if not completed or completed[-1] + 1 >= len(sessions):
            self.message = '거래 달력 범위 밖: 신규 진입 차단'
            return
        index = completed[-1]
        session, following = sessions[index:index + 2]
        if now < self.next_collect or self.control.get('collected_session') == session.day:
            return
        self.next_collect = now + timedelta(minutes=5)
        output = self.directory / 'receipts' / now.strftime('%Y%m%dT%H%M%S%fZ')
        _ = collect_receipt(output, self.protocol.path.parent / 'sessions.csv', clock=self.clock)
        observed = self.clock()
        receipt = read_receipt(output / 'receipt.json', self.protocol, observed)
        if isinstance(self.backend, LocalOperatingSession):
            self.backend.consume(receipt, observed, entries_allowed=not self.entries_paused)
            if self.backend.status().get('last_session') != session.day:
                self.message = str(self.backend.status().get('message', '자료 부족'))
                return
        else:
            fresh = self.started_at is not None and utc(session.close_at) > self.started_at
            if fresh or self.control.get('broker_bootstrapped') is True:
                _ = self.backend.evaluate_completed(receipt.bars, observed_at=observed,
                    signal_session=session, next_session=following,
                    entries_allowed=not self.entries_paused and not receipt.failures
                    and not receipt.split_dates and observed < utc(following.open_at))
            self.control['broker_bootstrapped'] = True
        self.control['collected_session'] = session.day
        self.message = '일봉 자료 수신/처리 완료; ' + ('로컬 모의 체결' if self.mode == 'local_paper' else 'KIS 모의 서버 체결 이력 확인')
        self._save_control()

    def status(self) -> OpsStatus:
        details = self.backend.status() if self.backend is not None else {}
        if self.backend is None and self.mode == 'local_paper' and (self.directory / 'local_paper' / 'CURRENT').exists():
            details = LocalOperatingSession(self.directory / 'local_paper', self.protocol).status()
        positions: list[Position] = []
        values = details.get('positions', [])
        if isinstance(values, list):
            for value in values:
                if isinstance(value, dict):
                    positions.append({'symbol': str(value.get('symbol', '')),
                        'qty': _number(value.get('qty')), 'market_value': _number(value.get('market_value')),
                        'avg_entry_price': _number(value.get('avg_entry_price', value.get('average_price'))),
                        'high_water_price': _number(value.get('high_water_price'))})
        pending = details.get('pending', details.get('pending_orders', 0))
        return {'mode': self.mode, 'running': self.running, 'entries_paused': self.entries_paused,
                'version': self.version, 'message': self.message,
                'account_message': str(details.get('message', '')),
                'cash': _number(details.get('cash', details.get('cash_usd')), STARTING_USD),
                'equity': _number(details.get('equity', details.get('equity_usd')), STARTING_USD),
                'positions': positions, 'pending': int(pending) if isinstance(pending, int) else 0,
                'blockers': _strings(details.get('blockers')), 'no_buy_reasons': _strings(details.get('no_buy_reasons')),
                'updated_at': str(details.get('updated_at', details.get('observed_at')) or '-'),
                'details': details}

    def live_review(self) -> dict[str, JsonValue]:
        request = self.control.get('live_request')
        return live_review(request if isinstance(request, dict) else None,
                           self.version)

    def record_live_request(self, account: str, allocation_usd: float,
                            loss_stop_pct: float, confirm: str) -> None:
        request = live_request(account, allocation_usd, loss_stop_pct, confirm)
        request['protocol_sha256'] = self.protocol.sha256
        self.control['live_request'] = request
        self._save_control()
        self.message = '실전 요청만 저장됨; 기존 P1 전략/세션 승인 미충족으로 주문은 계속 차단'

    def close(self) -> None:
        self.running = False
        try:
            if self.backend is not None:
                self._save_control()
                self.backend.close()
        finally:
            self.backend = None
            self.resources.close()
            self.guard.release()
        self.message = '종료됨; 브로커 미체결은 남아 있을 수 있으며 보호 판단은 중단됨'


def _number(value: JsonValue, default: float = 0) -> float:
    return float(value) if isinstance(value, (float, int)) and not isinstance(value, bool) else default


def _strings(value: JsonValue) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []
