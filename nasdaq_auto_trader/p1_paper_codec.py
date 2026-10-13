from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, fields
from math import isfinite
from typing import Final, Literal, TypeAlias, assert_never

from .backtest_execution import PendingOrder
from .backtest_types import BacktestRejection, BacktestTrade, EquityPoint
from .entry_policy_experiment_models import EntryDecisionRecord
from .experimental_exit_models import ExitDiagnostics
from .models import Bar, OrderRequest, Position, TradeDecision
from .p1_paper_models import (
    EntryRiskRecord,
    PaperAccountError,
    PaperFillRecord,
    PaperState,
    RiskState,
    StrategyState,
    bar_digest,
    bar_identity,
    timestamp,
    validate_bar,
)
from .profitability_risk import AcceptedOrder, EntryConstraintRecord
from .sizing_entry_risk import SizingRecord

JsonValue: TypeAlias = str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']
StateRow: TypeAlias = (Bar | Position | OrderRequest | TradeDecision | PendingOrder
    | BacktestTrade | BacktestRejection | EquityPoint | EntryDecisionRecord | ExitDiagnostics
    | AcceptedOrder | EntryConstraintRecord | SizingRecord | EntryRiskRecord | PaperFillRecord
    | StrategyState | RiskState | PaperState)
StateValue: TypeAlias = (str | int | float | bool | None | StateRow | list['StateValue']
    | tuple['StateValue', ...] | dict[str, 'StateValue'])
ROW_TYPES: Final[dict[str, type[StateRow]]] = {kind.__name__: kind for kind in (
    Bar, Position, OrderRequest, TradeDecision, PendingOrder, BacktestTrade,
    BacktestRejection, EquityPoint, EntryDecisionRecord, ExitDiagnostics,
    AcceptedOrder, EntryConstraintRecord, SizingRecord, EntryRiskRecord,
    PaperFillRecord, StrategyState, RiskState, PaperState,
)}
MAX_STATE_BYTES: Final = 32 * 1024 * 1024
ScalarType: TypeAlias = Literal['str', 'bool', 'int', 'float', 'Action', 'OrderSide', 'EntryPolicyName']
SCALAR_TYPES: Final[dict[str, ScalarType]] = {
    'str': 'str', 'bool': 'bool', 'int': 'int', 'float': 'float',
    'Action': 'Action', 'OrderSide': 'OrderSide', 'EntryPolicyName': 'EntryPolicyName',
}


def _pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise PaperAccountError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise PaperAccountError('nonfinite JSON constant: ' + value)


def read_json(payload: str) -> JsonValue:
    if len(payload.encode('utf-8')) > MAX_STATE_BYTES:
        raise PaperAccountError('paper state exceeds 32 MiB')
    try:
        value: JsonValue = json.loads(payload, object_pairs_hook=_pairs, parse_constant=_constant)
    except (json.JSONDecodeError, RecursionError) as error:
        raise PaperAccountError('invalid paper state JSON') from error
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 500000 or depth > 24:
            raise PaperAccountError('paper state nesting or node limit exceeded')
        match item:
            case dict():
                pending.extend((child, depth + 1) for child in item.values())
            case list():
                pending.extend((child, depth + 1) for child in item)
            case float() if not isfinite(item):
                raise PaperAccountError('nonfinite paper state number')
            case str() | int() | float() | bool() | None:
                continue
            case unreachable:
                assert_never(unreachable)
    return value


def _row[T: StateRow](value: JsonValue, model: type[T]) -> T:
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(model)}:
        raise PaperAccountError('invalid fields for ' + model.__name__)
    converted = {field.name: _value(value[field.name], str(field.type)) for field in fields(model)}
    return _construct(model, converted)


def _construct[T: StateRow](factory: Callable[..., T], values: dict[str, StateValue]) -> T:
    return factory(**values)


def _value(value: JsonValue, schema: str) -> StateValue:
    if schema.endswith(' | None'):
        return None if value is None else _value(value, schema.removesuffix(' | None'))
    if schema.startswith(('list[', 'tuple[')):
        if not isinstance(value, list):
            raise PaperAccountError('expected array for ' + schema)
        item_type = schema[schema.index('[') + 1:-1].removesuffix(', ...')
        result = [_value(item, item_type) for item in value]
        return tuple(result) if schema.startswith('tuple[') else result
    if schema.startswith('dict[str, '):
        if not isinstance(value, dict):
            raise PaperAccountError('expected mapping for ' + schema)
        return {key: _value(item, schema[10:-1]) for key, item in value.items()}
    if schema in ROW_TYPES:
        return _row(value, ROW_TYPES[schema])
    scalar = SCALAR_TYPES.get(schema)
    if scalar is None:
        raise PaperAccountError('unknown state field schema: ' + schema)
    match scalar:
        case 'str':
            if isinstance(value, str):
                return value
        case 'bool':
            if type(value) is bool:
                return value
        case 'int':
            if type(value) is int:
                return value
        case 'float':
            if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value):
                return float(value)
        case 'Action':
            if value in ('buy', 'sell', 'hold'):
                return value
        case 'OrderSide':
            if value in ('buy', 'sell'):
                return value
        case 'EntryPolicyName':
            if value in ('A', 'B', 'C'):
                return value
        case unreachable:
            assert_never(unreachable)
    raise PaperAccountError('invalid value for ' + schema)


def encode_state(state: PaperState) -> str:
    raw = json.dumps(asdict(state), allow_nan=False)
    canonical = _row(read_json(raw), PaperState)
    payload = json.dumps(asdict(canonical), allow_nan=False, sort_keys=True, separators=(',', ':'))
    if len(payload.encode('utf-8')) > MAX_STATE_BYTES:
        raise PaperAccountError('paper state exceeds 32 MiB')
    return payload


def decode_state(payload: str) -> PaperState:
    state = _row(read_json(payload), PaperState)
    if state.version != 1 or state.starting_cash <= 0 or state.cash < 0:
        raise PaperAccountError('invalid account state version or cash')
    if set(state.positions) != set(state.entry_fees) or set(state.positions) != set(state.position_risk):
        raise PaperAccountError('position fee/risk state mismatch')
    if set(state.pending) != set(state.actual_decisions):
        raise PaperAccountError('pending decision time state mismatch')
    expected: dict[str, str] = {}
    for symbol, history in state.histories.items():
        previous = None
        for bar in history:
            validate_bar(bar)
            stamp = timestamp(bar.timestamp)
            if bar.symbol != symbol or (previous is not None and stamp <= previous):
                raise PaperAccountError('invalid persisted history order')
            expected[bar_identity(bar)] = bar_digest(bar)
            previous = stamp
    if expected != state.processed:
        raise PaperAccountError('history and processed hashes disagree')
    for symbol, position in state.positions.items():
        if (position.symbol != symbol or position.qty <= 0 or not position.qty.is_integer()
                or position.avg_entry_price <= 0 or position.market_value <= 0):
            raise PaperAccountError('invalid persisted position')
    for symbol, order in state.pending.items():
        if symbol != order.order.symbol or symbol != order.decision.symbol or order.cash < 0 or order.risk < 0:
            raise PaperAccountError('invalid persisted pending order')
        decision_time = timestamp(state.actual_decisions[symbol])
        if (order.order.qty is None or order.order.qty <= 0 or not order.order.qty.is_integer()
                or order.order.notional is not None or order.order.time_in_force != 'day'
                or order.order.type not in ('market', 'limit')
                or not timestamp(order.timestamp) <= decision_time <= timestamp(state.observed_at)):
            raise PaperAccountError('invalid pending quantity, type, or decision time')
    for values in (state.entry_fees, state.position_risk):
        if any(number < 0 for number in values.values()):
            raise PaperAccountError('negative retained fee or risk')
    if len(state.trades) != len(state.fill_records):
        raise PaperAccountError('fill evidence count mismatch')
    for index, evidence in enumerate(state.fill_records):
        trade = state.trades[index]
        if (evidence.trade_index != index or not evidence.simulated
                or (evidence.symbol, evidence.side, evidence.signal_timestamp)
                != (trade.symbol, trade.side, trade.signal_timestamp)
                or timestamp(evidence.actual_decision_at) >= timestamp(evidence.logical_session_open)):
            raise PaperAccountError('invalid simulated fill evidence')
    previous_curve = None
    for point in state.equity_curve:
        stamp = timestamp(point.timestamp)
        if (previous_curve is not None and stamp <= previous_curve) or stamp > timestamp(state.observed_at):
            raise PaperAccountError('invalid persisted equity chronology')
        if abs(point.equity - point.cash - point.positions_value) > 1e-8:
            raise PaperAccountError('inconsistent persisted equity components')
        previous_curve = stamp
    if state.observed_at:
        timestamp(state.observed_at)
    return state


