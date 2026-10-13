"""Manual P1 commands routed by the existing network-blocked comparison CLI."""
from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .exit_experiment_config import ExperimentInputError
from .file_lock import exclusive_file_lock
from .p1_paper_inputs import read_receipt
from .p1_paper_protocol import digest, load_protocol
from .p1_paper_session import (
    account_status,
    apply_receipt,
    new_account_state,
    record_event,
)
from .p1_paper_store import read_checkpoint, write_checkpoint


class PaperArguments(argparse.Namespace):
    p1_paper: str = ''
    paper_dir: Path = Path('.')
    protocol: Path = Path('experiments/p1_paper_v1/protocol.json')
    receipt: Path | None = None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description='P1 ONLY: manual persistent simulated account; no live broker')
    _ = parser.add_argument('--p1-paper', choices=('init', 'resume', 'status'), required=True)
    _ = parser.add_argument('--paper-dir', type=Path, required=True)
    _ = parser.add_argument('--protocol', type=Path, default=Path('experiments/p1_paper_v1/protocol.json'))
    _ = parser.add_argument('--receipt', type=Path)
    args = parser.parse_args(argv, namespace=PaperArguments())
    directory = args.paper_dir.resolve()
    research = (Path(os.environ['LOCALAPPDATA']) / 'NasdaqAutoTrader/research').resolve()
    if directory == research or not directory.is_relative_to(research) or directory.is_symlink():
        parser.error('paper-dir must be a separate directory inside LOCALAPPDATA/NasdaqAutoTrader/research')
    protocol = load_protocol(args.protocol.resolve())
    action = args.p1_paper
    if action != 'init' and not (directory / 'CURRENT').is_file():
        parser.error('paper account not initialized; init is explicit and never overwrites an account')
    if action == 'resume' and args.receipt is None:
        parser.error('resume requires --receipt from the explicit public collector')
    if action != 'init' and digest(directory / 'protocol.json') != protocol.sha256:
        raise ExperimentInputError('paper_account_protocol_copy_corrupt')
    rejected = False
    now = datetime.now(UTC)
    with exclusive_file_lock(directory / '.lock', timeout_seconds=0):
        match action:
            case 'init':
                if any(p.name != '.lock' for p in directory.iterdir()):
                    raise ExperimentInputError('paper_init_requires_fresh_directory')
                state = new_account_state(protocol, now)
                _ = (directory / 'protocol.json').write_bytes(protocol.path.read_bytes())
                checkpoint = write_checkpoint(directory, state, None)
            case 'resume':
                if args.receipt is None:
                    parser.error('resume requires --receipt')
                previous, state = read_checkpoint(directory)
                _ = account_status(state, protocol, now)
                candidate = copy.deepcopy(state)
                try:
                    receipt = read_receipt(args.receipt, protocol, now)
                    changed = apply_receipt(candidate, protocol, receipt, now)
                except (ExperimentInputError, ValueError, OSError, KeyError) as error:
                    rejected = True
                    candidate = copy.deepcopy(state)
                    # Market input faults preserve positions and stops; source/protocol drift was checked earlier.
                    record_event(candidate, now, ['input_rejected:' + type(error).__name__, str(error)], fault=True)
                    changed = True
                checkpoint = write_checkpoint(directory, candidate, previous) if changed else previous
                state = candidate
            case 'status':
                checkpoint, state = read_checkpoint(directory)
            case _:
                parser.error('unknown paper command')
        if digest(directory / 'protocol.json') != protocol.sha256:
            raise ExperimentInputError('paper_account_protocol_copy_corrupt')
        result = account_status(state, protocol, now)
        result['input_rejected'] = rejected
        result['checkpoint'] = checkpoint
        result['paper_directory'] = str(directory)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 1 if rejected else 0
