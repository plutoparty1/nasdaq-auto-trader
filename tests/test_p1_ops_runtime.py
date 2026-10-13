from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader.p1_ops_local import LocalOperatingSession
from nasdaq_auto_trader.p1_ops_security import live_request, paper_credentials
from tests.test_p1_paper_session import protocol, receipt


def test_local_bootstrap_restart_and_duplicate_do_not_replay(tmp_path: Path) -> None:
    spec = protocol()
    now = datetime.fromisoformat(spec.sessions[64].close_at) + timedelta(minutes=10)
    local = LocalOperatingSession(tmp_path, spec)
    local.consume(receipt(spec, 64, 'warmup'), now, entries_allowed=True)
    assert local.status()['completed_sessions'] == 0
    assert local.status()['pending'] == 0
    next_now = datetime.fromisoformat(spec.sessions[65].close_at) + timedelta(minutes=10)
    local.consume(receipt(spec, 65, 'new'), next_now, entries_allowed=False)
    before = local.status()
    restarted = LocalOperatingSession(tmp_path, spec)
    restarted.consume(receipt(spec, 65, 'duplicate'), next_now, entries_allowed=True)
    assert restarted.status() == before
    assert restarted.status()['completed_sessions'] == 1


def test_gap_not_replayed_and_no_history_profit(tmp_path: Path) -> None:
    spec = protocol()
    local = LocalOperatingSession(tmp_path, spec)
    for index in (64, 68):
        now = datetime.fromisoformat(spec.sessions[index].close_at) + timedelta(minutes=10)
        local.consume(receipt(spec, index, str(index)), now, entries_allowed=True)
    assert local.status()['completed_sessions'] == 1
    assert 'missed_sessions' in str(local.status()['message'])


def test_paper_credentials_never_fall_back_to_generic() -> None:
    with pytest.raises(ValueError, match='dedicated_paper_credentials_required'):
        paper_credentials({'KIS_APP_KEY': 'real', 'KIS_APP_SECRET': 'real', 'KIS_ACCOUNT_NO': 'real'})
    value = paper_credentials({'KIS_PAPER_APP_KEY': 'demo', 'KIS_PAPER_APP_SECRET': 'demo', 'KIS_PAPER_ACCOUNT_NO': '12345678'})
    assert value.paper and value.app_key == 'demo'


def test_live_consent_is_bounded_request_not_authorization() -> None:
    with pytest.raises(ValueError):
        live_request('12345678', float('nan'), .02, '')
    request = live_request('12345678', 50, .02, '실전 위험과 미검증 상태를 확인했습니다')
    assert request['approved_for_orders'] is False
    assert request['account_masked'] == '****5678'
    assert '12345678' not in str(request)


def test_pointer_loss_does_not_reset_account(tmp_path: Path) -> None:
    spec = protocol()
    LocalOperatingSession(tmp_path, spec)
    (tmp_path / 'CURRENT').unlink()
    with pytest.raises(ValueError, match='pointer_missing'):
        LocalOperatingSession(tmp_path, spec)


def test_failed_publish_restores_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import nasdaq_auto_trader.p1_ops_local as module
    spec = protocol()
    local = LocalOperatingSession(tmp_path, spec)
    before = local.status()
    def fail(*args: object) -> str:
        raise OSError('synthetic_disk_failure')
    monkeypatch.setattr(module, 'write_checkpoint', fail)
    now = datetime.fromisoformat(spec.sessions[64].close_at) + timedelta(minutes=10)
    with pytest.raises(OSError):
        local.consume(receipt(spec, 64, 'one'), now, entries_allowed=True)
    assert local.status() == before


def test_controller_start_pause_restart_and_live_block(tmp_path: Path) -> None:
    from nasdaq_auto_trader.p1_ops_controller import P1OperatingController
    spec = protocol()
    controller = P1OperatingController(tmp_path, spec, process_check=lambda: None)
    controller.start('local_paper')
    controller.pause_entries()
    assert controller.status()['running'] and controller.status()['entries_paused']
    competitor = P1OperatingController(tmp_path, spec, process_check=lambda: None)
    with pytest.raises(ValueError, match='already_running'):
        competitor.start('local_paper')
    controller.close()
    restarted = P1OperatingController(tmp_path, spec, process_check=lambda: None)
    restarted.start('local_paper')
    assert restarted.status()['entries_paused']
    restarted.resume_entries()
    assert not restarted.status()['entries_paused']
    restarted.close()
    with pytest.raises(ValueError, match='approval_binding_unavailable'):
        restarted.start('live')
    assert restarted.status()['running'] is False


def test_controller_clock_reversal_blocks_entries(tmp_path: Path) -> None:
    from nasdaq_auto_trader.p1_ops_controller import P1OperatingController
    spec = protocol()
    now = datetime.fromisoformat(spec.sessions[64].close_at)
    controller = P1OperatingController(tmp_path, spec, clock=lambda: now, process_check=lambda: None)
    controller.start('local_paper')
    controller.last_tick = now + timedelta(minutes=1)
    with pytest.raises(ValueError, match='clock_moved_backwards'):
        controller.step()
    assert controller.entries_paused
    controller.close()


def test_controller_collects_once_and_preserves_pause(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nasdaq_auto_trader import p1_ops_controller as module
    spec = protocol()
    now = datetime.fromisoformat(spec.sessions[64].close_at) + timedelta(minutes=10)
    calls: list[Path] = []
    def collect(output: Path, calendar: Path, **kwargs: object) -> None:
        calls.append(output)
    monkeypatch.setattr(module, 'collect_receipt', collect)
    monkeypatch.setattr(module, 'read_receipt', lambda *args: receipt(spec, 64, 'synthetic'))
    controller = module.P1OperatingController(tmp_path, spec, clock=lambda: now, process_check=lambda: None)
    controller.start('local_paper')
    controller.pause_entries()
    controller.step()
    controller.step()
    assert len(calls) == 1
    assert controller.status()['entries_paused']
    controller.close()
    restarted = module.P1OperatingController(tmp_path, spec, clock=lambda: now, process_check=lambda: None)
    restarted.start('local_paper')
    restarted.step()
    assert len(calls) == 1
    assert restarted.last_tick == now
    restarted.close()


def test_checkpoint_retry_is_bounded_and_does_not_retry_other_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nasdaq_auto_trader import p1_ops_checkpoint as module
    calls: list[int] = []
    def transient(*args: object) -> str:
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError('synthetic_publication_sharing')
        return 'committed'
    monkeypatch.setattr(module, 'publish_checkpoint', transient)
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    assert module.write_checkpoint(tmp_path, {'schema_version': 1}, None) == 'committed'
    assert len(calls) == 3
    def permanent(*args: object) -> str:
        calls.append(1)
        raise PermissionError('synthetic_permanent_failure')
    calls.clear()
    monkeypatch.setattr(module, 'publish_checkpoint', permanent)
    with pytest.raises(PermissionError):
        module.write_checkpoint(tmp_path, {'schema_version': 1}, None)
    assert len(calls) == 5


def test_changed_operating_version_cannot_resume_same_account(tmp_path: Path) -> None:
    from nasdaq_auto_trader.p1_ops_controller import P1OperatingController
    spec = protocol()
    first = P1OperatingController(tmp_path, spec, process_check=lambda: None)
    first.start('local_paper'); first.close()
    changed = P1OperatingController(tmp_path, spec, process_check=lambda: None)
    changed.version = 'p1-ops-changed'
    with pytest.raises(ValueError, match='new_state_version'):
        changed.start('local_paper')
