from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path

from .file_lock import FileLockTimeout, exclusive_file_lock


class SingleInstanceGuard:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._held_lock: AbstractContextManager[None] | None = None

    def acquire(self) -> bool:
        if self._held_lock is not None:
            return True
        candidate = exclusive_file_lock(self.path, 0.0)
        try:
            candidate.__enter__()
        except FileLockTimeout:
            return False
        self._held_lock = candidate
        return True

    def release(self) -> None:
        held = self._held_lock
        if held is None:
            return
        self._held_lock = None
        held.__exit__(None, None, None)
