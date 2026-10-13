from __future__ import annotations

from typing import Final, assert_never

from .automation_coordinator import TransitionResult
from .operating_state import OperatingState
from .quant_data.symbol_selector import (
    ResolvedStrategy,
    StrategyResolution,
    StrategyResolutionBlock,
)
from .selection_presenter import selection_reason_label

_WAIT_REASONS: Final = {
    'weekend': '주말 장외 대기',
    'market_holiday': '휴장일 대기',
    'before_regular_open': '정규장 시작 전 대기',
    'after_regular_close': '정규장 종료 후 대기',
    'reconciliation_required': '장 종료 후 계좌 확인',
    'operating_model_unavailable': '사용 가능한 전략이 없어 장중 무주문 스캔',
}


def operating_wait_lines(
    transition: TransitionResult | None, resolution: StrategyResolution | None,
) -> tuple[str, ...]:
    """Describe an observed wait without inferring unperformed order checks."""
    if transition is None:
        return ()
    match transition.state:
        case (
            OperatingState.IDLE | OperatingState.PRE_MARKET_CHECK
            | OperatingState.POST_MARKET_RECONCILIATION | OperatingState.INTRADAY_SHADOW_SCAN
        ):
            state_line = (
                f'자동운영: {_WAIT_REASONS.get(transition.reason, transition.reason)} '
                f'[{transition.state.value}]'
            )
        case (
            OperatingState.LIVE_TRADING | OperatingState.OFF_HOURS_LEARNING
            | OperatingState.MANUAL_TRAIN_ONLY | OperatingState.SAFE_HALT
            | OperatingState.EMERGENCY_STOP
        ):
            return ()
        case unreachable:
            assert_never(unreachable)
    match resolution:
        case ResolvedStrategy():
            strategy_line = (
                f'해석된 학습 전략: {resolution.spec.strategy_id} '
                f'{resolution.spec.version} [{resolution.registry_status.value}]'
            )
        case StrategyResolutionBlock():
            strategy_line = (
                f'전략 사용 불가: {selection_reason_label(resolution.reason)} '
                f'[{resolution.reason}]'
            )
        case None:
            strategy_line = '학습 전략 확인: 이번 주기 미평가 (자동 종목 선택 미사용)'
        case unreachable:
            assert_never(unreachable)
    return (
        state_line,
        strategy_line,
        '매수 신호·수량/현금/위험·주문 승인·주문용 시세: 미평가 (거래 실행 단계 미진입)',
    )
