from __future__ import annotations

from typing import Final


RECOVERABLE_PREORDER_REASONS: Final = frozenset(
    {
        "market_data_unavailable",
        "broker_unavailable",
        "account_state_unavailable",
    }
)


def is_recoverable_preorder_failure(reason: str) -> bool:
    return reason in RECOVERABLE_PREORDER_REASONS
