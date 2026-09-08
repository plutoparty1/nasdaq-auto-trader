"""Run the CLI with python -m nasdaq_auto_trader."""

from __future__ import annotations

import sys

from .config import ConfigLoadError, TradingModeValidationError
from .cli_types import CliCommandError
from .data import CsvFileError, InvalidCsvDataError, MissingCsvColumnsError
from .live_canary_admin import ArmIssueError
from .cli_live_canary import LiveCanaryCliError


def main() -> int:
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "ai-quant":
            from .ai_quant_lab.operator_cli import main as ai_quant_main

            return ai_quant_main(sys.argv[2:])
        from .cli import main as legacy_main

        return legacy_main()
    except (
        ArmIssueError,
        CliCommandError,
        ConfigLoadError,
        CsvFileError,
        InvalidCsvDataError,
        LiveCanaryCliError,
        MissingCsvColumnsError,
        TradingModeValidationError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
