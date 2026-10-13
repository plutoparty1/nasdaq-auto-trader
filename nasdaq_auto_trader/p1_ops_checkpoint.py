"""Bounded retry of Windows checkpoint publication; never retries a broker request."""
from __future__ import annotations

import time
from pathlib import Path

from .entry_comparison import JsonValue
from .p1_paper_store import write_checkpoint as publish_checkpoint


def write_checkpoint(directory: Path, state: dict[str, JsonValue], previous: str | None) -> str:
    for attempt in range(5):
        try:
            return publish_checkpoint(directory, state, previous)
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep((.02, .04, .08, .16)[attempt])
    raise RuntimeError('unreachable_checkpoint_retry')
