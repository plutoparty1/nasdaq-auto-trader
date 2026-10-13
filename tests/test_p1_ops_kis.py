from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request

import pytest

from nasdaq_auto_trader.brokers.kis_client import KISClient, KISCredentials
from nasdaq_auto_trader.entry_comparison import JsonValue
from nasdaq_auto_trader.live_canary_lease import BrokerLiveLease
from nasdaq_auto_trader.models import OrderRequest
from nasdaq_auto_trader.p1_ops_kis import P1OperatingKISClient, P1SubmissionBlocked


def client(tmp_path: Path, current: list[datetime]) -> P1OperatingKISClient:
    result = P1OperatingKISClient(KISCredentials('synthetic-key', 'synthetic-secret', '00000000'),
                                  tmp_path / 'token.json', clock=lambda: current[0])
    result._access_token = 'synthetic-token'
    result._token_expires_at = datetime(2099, 1, 1, tzinfo=UTC)
    result._broker_lease_path = tmp_path / 'lease.lock'
    return result


def order() -> OrderRequest:
    return OrderRequest('HIVE', 'buy', type='limit', qty=2.0, limit_price=2.0)


@pytest.mark.parametrize('delay_stage', ['none', 'account', 'power', 'authentication', 'exact_deadline'])
def test_wire_guard_checks_clock_after_internal_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                      delay_stage: str) -> None:
    # Given a real KIS client with synthetic transport and an opening deadline.
    opened = datetime(2026, 10, 12, 13, 30, tzinfo=UTC)
    deadline = opened + timedelta(minutes=5)
    current = [deadline - timedelta(seconds=1)]
    broker = client(tmp_path, current)
    mutations: list[str] = []

    def transport(self: KISClient, request: Request, label: str) -> dict[str, JsonValue]:
        path = urlsplit(request.full_url).path
        if path.endswith('inquire-present-balance'):
            if delay_stage == 'account':
                current[0] = deadline + timedelta(seconds=1)
            return {'output2': [{'crcy_cd': 'USD', 'frcr_dncl_amt_2': '100'}]}
        if path.endswith('inquire-psamount'):
            if delay_stage in ('power', 'exact_deadline'):
                current[0] = deadline + timedelta(seconds=int(delay_stage == 'power'))
            return {'output': {'ovrs_ord_psbl_amt': '100'}}
        mutations.append(path)
        return {'rt_cd': '0', 'output': {'ODNO': 'synthetic-order'}}

    def authenticate() -> None:
        current[0] = deadline + timedelta(seconds=1)

    monkeypatch.setattr(KISClient, '_open_json', transport)
    if delay_stage == 'authentication':
        monkeypatch.setattr(broker, '_ensure_token', authenticate)
    with BrokerLiveLease.acquire(broker._broker_lease_path, broker.account_fingerprint,
                                 frozenset({'buy', 'sell'})) as lease:
        broker.bind_live_lease(lease)
        broker.bind_submission_window(order(), opened, deadline)
        # When inherited submit_order performs its own fresh reads before the POST.
        if delay_stage == 'none':
            assert broker.submit_order(order())['rt_cd'] == '0'
        else:
            with pytest.raises(P1SubmissionBlocked, match='submission_window_elapsed'):
                broker.submit_order(order())
    # Then only the still-current request can reach the synthetic wire.
    assert len(mutations) == int(delay_stage == 'none')
    assert not (tmp_path / 'token.json').exists()
    with pytest.raises(P1SubmissionBlocked, match='submission_window_missing'):
        broker.submit_order(order())


def test_transport_requires_window_lease_and_matching_order(tmp_path: Path) -> None:
    # Given a paper client without an active operation binding.
    opened = datetime(2026, 10, 12, 13, 30, tzinfo=UTC)
    broker = client(tmp_path, [opened])
    # When direct submission lacks the operation window or lifetime lease.
    with pytest.raises(P1SubmissionBlocked, match='submission_window_missing'):
        broker.submit_order(order())
    broker.bind_submission_window(order(), opened, opened + timedelta(minutes=5))
    with pytest.raises(P1SubmissionBlocked, match='submission_lease_required'):
        broker.submit_order(order())
    broker.bind_submission_window(order(), opened, opened + timedelta(minutes=5))
    with pytest.raises(P1SubmissionBlocked, match='submission_order_mismatch'):
        broker.submit_order(OrderRequest('KDP', 'buy', type='limit', qty=2, limit_price=2))
    # Then none of these paths can reach the existing client transport.
    assert not (tmp_path / 'token.json').exists()


@pytest.mark.parametrize('path', ['/uapi/overseas-stock/v1/trading/order-rvsecncl', '/unexpected'])
def test_transport_denies_cancellation_and_other_mutations(tmp_path: Path, path: str) -> None:
    # Given a paper transport with an unsupported mutation URL.
    broker = client(tmp_path, [datetime(2026, 10, 12, tzinfo=UTC)])
    # When a caller bypasses submit_order and reaches the wire boundary.
    with pytest.raises(P1SubmissionBlocked, match='submission_mutation_forbidden'):
        broker._open_json(Request(broker.paper_base_url + path, data=b'{}', method='POST'), 'synthetic')
    # Then it is rejected before transport or token access.
    assert not (tmp_path / 'token.json').exists()


def test_real_mode_and_real_host_cannot_reach_transport(tmp_path: Path) -> None:
    # Given real credentials or a modified paper client's host.
    with pytest.raises(P1SubmissionBlocked, match='paper_mode_required'):
        P1OperatingKISClient(KISCredentials('synthetic', 'synthetic', '00000000', paper=False))
    broker = client(tmp_path, [datetime(2026, 10, 12, tzinfo=UTC)])
    # When a request points at the live host.
    with pytest.raises(P1SubmissionBlocked, match='paper_host_required'):
        broker._open_json(Request(broker.real_base_url + '/anything'), 'synthetic')
    # Then no token cache or request is made.
    assert not (tmp_path / 'token.json').exists()


def test_delayed_accepted_wire_time_matches_confirmed_history(tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the real guarded client whose internal buying-power read takes 45 seconds.
    from nasdaq_auto_trader.brokers.kis_reconciliation import KISOrderHistory
    from nasdaq_auto_trader.models import Position
    from nasdaq_auto_trader.p1_ops_broker import BrokerOperatingSession
    from tests.test_p1_ops_broker import FakeBroker, sample_bars, spec

    protocol, fake = spec(), FakeBroker()
    opened = datetime.fromisoformat(protocol.sessions[71].open_at)
    current = [opened]
    broker = client(tmp_path, current)
    mutations: list[str] = []

    def power(symbol: str, order_price: float | None = None) -> float:
        current[0] += timedelta(seconds=45)
        return fake.cash

    def transport(self: KISClient, request: Request, label: str) -> dict[str, JsonValue]:
        mutations.append(request.get_method())
        return {'rt_cd': '0', 'output': {'ODNO': 'synthetic-order'}}

    monkeypatch.setattr(broker, 'get_account', fake.get_account)
    monkeypatch.setattr(broker, 'list_positions', fake.list_positions)
    monkeypatch.setattr(broker, 'list_open_orders', fake.list_open_orders)
    monkeypatch.setattr(broker, 'list_order_history', fake.list_order_history)
    monkeypatch.setattr(broker, 'get_overseas_buying_power', power)
    monkeypatch.setattr(KISClient, '_open_json', transport)
    with BrokerLiveLease.acquire(broker._broker_lease_path, broker.account_fingerprint,
                                 frozenset({'buy', 'sell'})) as lease:
        broker.bind_live_lease(lease)
        session = BrokerOperatingSession(tmp_path / 'ops', protocol, broker, clock=lambda: current[0])
        session.evaluate_completed(sample_bars(protocol), datetime.fromisoformat(protocol.sessions[70].close_at),
                                   protocol.sessions[70], protocol.sessions[71], True)
        session.tick(opened, True)
        intent = next(iter(session.store.state.intents.values()))
        fake.history = (KISOrderHistory('synthetic-order', 'HIVE', 'buy', intent.qty, 2, 2.07,
                                       'unknown', current[0]),)
        fake.positions['HIVE'] = Position('HIVE', 2, 4.14, 2.07)
        fake.cash = 100 - 4.14 * 1.0025
        session.close()
        session = BrokerOperatingSession(tmp_path / 'ops', protocol, broker, clock=lambda: current[0])
        # When restart reconciles history carrying the actual delayed wire timestamp.
        session.tick(current[0] + timedelta(seconds=1), True)
    # Then the returned identity and bounded response interval confirm only that fill.
    assert mutations == ['POST']
    assert session.status()['positions'][0]['qty'] == 2
    assert session.status()['orders'][0]['status'] == 'partial'
