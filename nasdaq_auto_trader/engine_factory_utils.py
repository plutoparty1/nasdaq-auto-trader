from __future__ import annotations

from inspect import Parameter, signature
from typing import Callable

from .engine import TradingEngine


def factory_accepts_argument(
    factory: Callable[..., TradingEngine],
    name: str,
) -> bool:
    try:
        parameters = signature(factory).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == name or parameter.kind == Parameter.VAR_KEYWORD
        for parameter in parameters
    )
