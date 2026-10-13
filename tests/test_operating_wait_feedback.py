from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nasdaq_auto_trader.ai_quant_lab.registry_models import StrategyStatus
from nasdaq_auto_trader.app_controller import AutoTradeController
from nasdaq_auto_trader.app_ui_render import DashboardRenderMixin
from nasdaq_auto_trader.automation_coordinator import AutomationCoordinator
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.operating_state import (
    OperatingState,
    OperatingStateStore,
    RuntimeState,
)
from nasdaq_auto_trader.quant_data.symbol_selector import (
    ResolvedStrategy,
    StrategyResolutionBlock,
)
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.ai_quant_fixtures import valid_spec
from tests.test_gui_auto_start_feedback import Variable


@pytest.mark.parametrize('stamp,expected_state,label', [
    ('2026-10-11T22:53:24+00:00', OperatingState.IDLE, '주말'),
    ('2026-10-12T13:00:00+00:00', OperatingState.PRE_MARKET_CHECK, '정규장 시작 전'),
])
def test_wait_feedback_keeps_approved_strategy_and_deferred_checks(
    tmp_path: Path, stamp: str, expected_state: OperatingState, label: str,
) -> None:
    # Given completed learning and an existing usable strategy before market open.
    now = datetime.fromisoformat(stamp)
    engine = Mock(side_effect=AssertionError('Broker engine must not be constructed'))
    controller = AutoTradeController(
        AppConfig(mode='dry_run'), engine_factory=engine, clock=lambda: now,
        trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
        session_store=TradingSessionStore(tmp_path / 'session.json'),
    )
    store = OperatingStateStore(tmp_path / 'operating.json')
    store.save(RuntimeState(OperatingState.IDLE, now, last_learning_market_date='2026-10-09'))
    controller.operating_store = store
    controller.operating_coordinator = AutomationCoordinator(store)
    resolved = ResolvedStrategy(valid_spec(), 'test-digest', StrategyStatus.CHAMPION)
    controller.start()
    view = DashboardRenderMixin()
    view.controller = controller
    view.status_var = Variable()
    logs: list[str] = []
    view._append_log = logs.append

    # When the real coordinator runs and its empty result is rendered.
    with patch('nasdaq_auto_trader.controller_operations.resolve_strategy', return_value=resolved):
        result = controller.run_operating_cycle(force=True)
    view._render_auto_results(result)

    # Then the wait reason is visible without pretending downstream checks ran.
    assert controller.last_operating_transition.state is expected_state
    assert controller.last_strategy_resolution == resolved
    assert label in '\n'.join(logs)
    assert resolved.spec.strategy_id in '\n'.join(logs)
    assert resolved.spec.version in '\n'.join(logs)
    assert '미평가' in '\n'.join(logs)
    assert not any('매매 결과 0개, 다음 주기 대기' in line for line in logs)
    engine.assert_not_called()


def test_wait_feedback_exposes_missing_approval_without_claiming_no_signal(tmp_path: Path) -> None:
    # Given an unresolved live strategy while the exchange is closed.
    now = datetime(2026, 10, 12, 13, tzinfo=UTC)
    engine = Mock(side_effect=AssertionError('Broker engine must not be constructed'))
    controller = AutoTradeController(
        AppConfig(mode='dry_run'), engine_factory=engine, clock=lambda: now,
        trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
        session_store=TradingSessionStore(tmp_path / 'session.json'),
    )
    store = OperatingStateStore(tmp_path / 'operating.json')
    store.save(RuntimeState(OperatingState.IDLE, now, last_learning_market_date='2026-10-09'))
    controller.operating_store = store
    controller.operating_coordinator = AutomationCoordinator(store)
    controller.start()
    view = DashboardRenderMixin()
    view.controller = controller
    view.status_var = Variable()
    logs: list[str] = []
    view._append_log = logs.append

    # When the cycle observes a specific missing approval.
    with patch('nasdaq_auto_trader.controller_operations.resolve_strategy', return_value=StrategyResolutionBlock('manual_approval_missing')):
        result = controller.run_operating_cycle(force=True)
    view._render_auto_results(result)

    # Then approval unavailability is separate from unperformed entry checks.
    assert '수동 승인이 없습니다' in '\n'.join(logs)
    assert '미평가' in '\n'.join(logs)
    assert '매수 신호 없음' not in '\n'.join(logs)
    engine.assert_not_called()


def test_history_failure_pauses_without_repeating_collection(tmp_path: Path) -> None:
    # Given a due learning run whose paging cursor cannot advance safely.
    from nasdaq_auto_trader.learning_history import LearningHistoryError

    now = datetime(2026, 10, 12, 13, tzinfo=UTC)
    engine = Mock(side_effect=AssertionError('Broker engine must not be constructed'))
    controller = AutoTradeController(
        AppConfig(mode='dry_run'), engine_factory=engine, clock=lambda: now,
        trading_settings=TradingSettings(unattended_operation_enabled=True),
        session_store=TradingSessionStore(tmp_path / 'session.json'),
    )
    store = OperatingStateStore(tmp_path / 'operating.json')
    store.save(RuntimeState(OperatingState.IDLE, now))
    controller.operating_store = store
    controller.operating_coordinator = AutomationCoordinator(store)
    controller.start()
    reason = 'learning_history_cursor_not_advancing'
    view = DashboardRenderMixin()
    view.controller = controller
    view.status_var = Variable()
    logs: list[str] = []
    view._append_log = logs.append

    # When a collection fault occurs and the GUI polls the same controller again.
    with patch.object(controller, '_execute_learning', side_effect=LearningHistoryError(reason, 'TEST')) as collect:
        result = controller.run_operating_cycle(force=True)
        view._render_auto_results(result)
        subsequent = controller.run_operating_cycle(force=True)

    # Then the specific reason remains visible and no repeated fetch is scheduled.
    assert result == []
    assert subsequent is None
    assert controller.state == 'paused'
    assert controller.next_run_at is None
    assert controller.is_due() is False
    assert controller.last_error == reason
    assert reason in '\n'.join(logs)
    assert collect.call_count == 1
    engine.assert_not_called()
