from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader import p1_ops_broker_store
from nasdaq_auto_trader.entry_comparison import JsonValue
from nasdaq_auto_trader.p1_ops_broker import BrokerOperatingSession
from nasdaq_auto_trader.p1_ops_broker_models import OperatingError
from tests.test_p1_ops_broker import Credentials, FakeBroker, sample_bars, spec


def test_truthy_callback_cannot_activate_live_mode(tmp_path: Path) -> None:
    # Given real-mode credentials and a callback that always claims authorization.
    broker = FakeBroker()
    broker.credentials = Credentials(paper=False)
    # When construction attempts to bypass the missing P1 authorization binding.
    with pytest.raises(OperatingError, match='p1_live_authorization_unavailable'):
        BrokerOperatingSession(tmp_path, spec(), broker, mode='kis_live', authorize_live=lambda _: True)
    # Then no live adapter or POST is created.
    assert not broker.submitted


@pytest.mark.parametrize('delay_stage', ['buying_power', 'checkpoint'])
def test_fresh_clock_expires_entry_after_slow_preparation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                        delay_stage: str) -> None:
    # Given a plan whose tick begins just inside the five minute opening window.
    broker, protocol = FakeBroker(), spec()
    opened = datetime.fromisoformat(protocol.sessions[71].open_at)
    current = [opened + timedelta(minutes=4, seconds=59)]
    session = BrokerOperatingSession(tmp_path, protocol, broker, clock=lambda: current[0])
    session.evaluate_completed(sample_bars(protocol), datetime.fromisoformat(protocol.sessions[70].close_at),
                               protocol.sessions[70], protocol.sessions[71], True)
    original_write = p1_ops_broker_store.write_checkpoint

    def power(symbol: str, order_price: float | None = None) -> float:
        current[0] = opened + timedelta(minutes=5, seconds=1)
        return broker.cash

    def write(directory: Path, state: dict[str, JsonValue], previous: str | None) -> str:
        result = original_write(directory, state, previous)
        if 'submitting' in repr(state):
            current[0] = opened + timedelta(minutes=5, seconds=1)
        return result

    if delay_stage == 'buying_power':
        monkeypatch.setattr(broker, 'get_overseas_buying_power', power)
    else:
        monkeypatch.setattr(p1_ops_broker_store, 'write_checkpoint', write)
    # When preparation crosses the submission deadline.
    session.tick(opened + timedelta(minutes=4, seconds=59), True)
    # Then the saved plan expires before any broker POST.
    assert not broker.submitted
    assert session.status()['orders'][0]['status'] == 'expired'
