from __future__ import annotations

from . import cli_commands_basic as _basic_commands
from . import cli_commands_special as _special_commands
from .cli_main import main as _main
from .cli_parser import build_parser
from .cli_types import CliCommandError, CliResult, JsonObject
from .engine import TradingEngine


def main(argv: list[str] | None = None) -> int:
    _basic_commands.TradingEngine = TradingEngine
    _special_commands.TradingEngine = TradingEngine
    return _main(argv)


__all__ = [
    "CliCommandError",
    "CliResult",
    "JsonObject",
    "TradingEngine",
    "build_parser",
    "main",
]
