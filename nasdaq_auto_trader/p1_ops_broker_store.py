from __future__ import annotations

from dataclasses import asdict
from json import dumps
from math import isfinite
from pathlib import Path
from typing import assert_never, final

from .entry_comparison import JsonValue
from .models import OrderSide, Position
from .p1_ops_broker_models import (
    Holding,
    Intent,
    OperatingError,
    OperatingState,
    OrderState,
)
from .p1_ops_checkpoint import write_checkpoint
from .p1_paper_account import PaperAccount
from .p1_paper_codec import read_json
from .p1_paper_protocol import STARTING_USD, PaperProtocol, mapping, text_field
from .p1_paper_store import read_checkpoint


def number(value: JsonValue) -> float:
    match value:
        case int() | float() if not isinstance(value, bool) and isfinite(value):
            return float(value)
        case str() | bool() | list() | dict() | None | int() | float():
            raise OperatingError('invalid_operating_number')
        case _:
            assert_never(value)


def integer(value: JsonValue) -> int:
    parsed = number(value)
    if parsed < 0 or not parsed.is_integer():
        raise OperatingError('invalid_operating_quantity')
    return int(parsed)


def flag(value: JsonValue) -> bool:
    if type(value) is not bool:
        raise OperatingError('invalid_operating_flag')
    return value


def string(value: JsonValue) -> str:
    if not isinstance(value, str):
        raise OperatingError('invalid_operating_text')
    return value


def strings(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        raise OperatingError('invalid_operating_list')
    return [string(item) for item in value]


def parse_intent(value: JsonValue) -> Intent:
    row = mapping(value)
    sides: dict[str, OrderSide] = {'buy': 'buy', 'sell': 'sell'}
    side = sides.get(string(row.get('side')))
    if side is None:
        raise OperatingError('invalid_operating_side')
    try:
        state = OrderState(string(row['state']))
    except ValueError as error:
        raise OperatingError('invalid_operating_order_state') from error
    result = Intent(text_field(row['key']), text_field(row['symbol']), side,
        text_field(row['signal_at']), text_field(row['evaluated_at']), text_field(row['open_at']),
        text_field(row['close_at']), number(row['limit_price']), number(row['stop_price']),
        integer(row['qty']), state, string(row['order_id']), string(row['submitted_at']),
        tuple(strings(row['prior_order_ids'])), integer(row['filled_qty']),
        number(row['filled_notional']), number(row['fee_estimate']), number(row['cash_before']),
        number(row['qty_before']), flag(row['awaiting_balance']), string(row['reason']),
        string(row.get('response_at', '')))
    if result.filled_qty > result.qty or result.limit_price <= 0 or result.fee_estimate < 0:
        raise OperatingError('invalid_operating_order_values')
    return result


def parse_state(value: JsonValue) -> OperatingState:
    row = mapping(value)
    state = OperatingState()
    for name in ('cash', 'costs', 'realized', 'maximum_loss', 'peak_equity', 'broker_start_cash',
                 'maximum_drawdown', 'previous_equity', 'day_start_equity'):
        setattr(state, name, number(row[name]))
    state.day, state.observed_at = string(row['day']), string(row['observed_at'])
    state.day_halted, state.initialized = flag(row['day_halted']), flag(row['initialized'])
    state.blockers, state.faults = strings(row['blockers']), strings(row['faults'])
    state.unsafe_symbols = strings(row['unsafe_symbols'])
    state.protection_blockers = strings(row['protection_blockers'])
    state.data_blockers = strings(row['data_blockers'])
    state.evaluated = {key: text_field(item) for key, item in mapping(row['evaluated']).items()}
    state.intents = {key: parse_intent(item) for key, item in mapping(row['intents']).items()}
    for key, item in mapping(row['holdings']).items():
        holding = mapping(item)
        state.holdings[key] = Holding(text_field(holding['symbol']), integer(holding['qty']),
            *(number(holding[name]) for name in ('average_price', 'stop_price', 'high_water_price',
                'mark_price', 'entry_fee', 'planned_risk')))
        if state.holdings[key].qty == 0 or key != state.holdings[key].symbol:
            raise OperatingError('invalid_operating_holding')
    for key, item in mapping(row['baseline']).items():
        prior = mapping(item)
        state.baseline[key] = Position(text_field(prior['symbol']), number(prior['qty']),
            number(prior['market_value']), number(prior['avg_entry_price']),
            None if prior['high_water_price'] is None else number(prior['high_water_price']))
    if any(key != intent.key for key, intent in state.intents.items()):
        raise OperatingError('invalid_operating_intent_key')
    return state


@final
class OperatingStore:
    def __init__(self, directory: Path, protocol: PaperProtocol, mode: str, identity: str) -> None:
        self.directory, self.protocol, self.mode, self.identity = directory, protocol, mode, identity
        self.checkpoint: str | None = None
        self.codec = PaperAccount(protocol.config, protocol.policy, protocol.costs['base'], STARTING_USD)
        self.state = OperatingState()
        directory.mkdir(parents=True, exist_ok=True)
        if (directory / 'CURRENT').exists():
            self.checkpoint, saved = read_checkpoint(directory)
            if (saved.get('kind'), saved.get('protocol'), saved.get('mode'), saved.get('identity')) != (
                    'p1-broker-ops-v1', protocol.sha256, mode, identity):
                raise OperatingError('operating_account_or_protocol_mismatch')
            self.codec.load_state(text_field(saved.get('strategy')))
            self.state = parse_state(saved.get('state'))
        elif any(directory.glob('checkpoint-*.json')):
            raise OperatingError('operating_checkpoint_pointer_missing')

    def save(self) -> None:
        payload: dict[str, JsonValue] = {'schema_version': 1, 'kind': 'p1-broker-ops-v1',
            'protocol': self.protocol.sha256, 'mode': self.mode, 'identity': self.identity,
            'strategy': self.codec.export_state(), 'state': read_json(dumps(vars(self.state), default=asdict, allow_nan=False))}
        self.checkpoint = write_checkpoint(self.directory, payload, self.checkpoint)
