from __future__ import annotations


class PreOrderCycleError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
