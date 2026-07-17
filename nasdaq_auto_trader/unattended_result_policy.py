from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def terminal_order_failure_reason(
    results: Iterable[Mapping[str, Any]],
) -> str | None:
    for result in results:
        response = result.get("response")
        if not isinstance(response, Mapping) or response.get("terminal") is not True:
            continue
        reason = response.get("reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
        return "terminal_order_response"
    return None
