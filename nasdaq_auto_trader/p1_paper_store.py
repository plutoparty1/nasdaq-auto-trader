"""Immutable paper checkpoints published through one atomic pointer under the existing lock."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Final

from .entry_comparison import JsonValue
from .exit_experiment_config import ExperimentInputError
from .p1_paper_codec import read_json
from .p1_paper_protocol import mapping

CHECKPOINT: Final = re.compile(r'checkpoint-[0-9]{6}-[0-9a-f]{16}\.json')


def read_checkpoint(directory: Path) -> tuple[str, dict[str, JsonValue]]:
    """Never silently reset or roll back a damaged account."""
    pointer = (directory / 'CURRENT').read_text(encoding='ascii').strip()
    if CHECKPOINT.fullmatch(pointer) is None:
        raise ExperimentInputError('paper_checkpoint_pointer_invalid')
    payload = (directory / pointer).read_bytes()
    if hashlib.sha256(payload).hexdigest()[:16] != pointer[-21:-5]:
        raise ExperimentInputError('paper_checkpoint_hash_mismatch')
    value = read_json(payload.decode('utf-8'))
    state = mapping(value)
    if state.get('schema_version') != 1:
        raise ExperimentInputError('paper_checkpoint_schema_invalid')
    return pointer, state


def write_checkpoint(directory: Path, state: dict[str, JsonValue], previous: str | None) -> str:
    """Commit account, cost books and input IDs together; interrupted publication is retryable."""
    revision = 0 if previous is None else int(previous.split('-')[1]) + 1
    current = {**state, 'previous_checkpoint': previous, 'revision': revision}
    payload = json.dumps(current, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')
    name = f'checkpoint-{revision:06d}-{hashlib.sha256(payload).hexdigest()[:16]}.json'
    destination = directory / name
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ExperimentInputError('paper_checkpoint_collision')
    else:
        with destination.open('xb') as handle:
            _ = handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    temporary = directory / 'CURRENT.tmp'
    with temporary.open('w', encoding='ascii') as handle:
        _ = handle.write(name + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, directory / 'CURRENT')
    return name
