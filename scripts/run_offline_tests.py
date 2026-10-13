# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest==9.1.1"]
# ///
"""Run regression tests with outbound sockets disabled for this process."""

# Run: python scripts/run_offline_tests.py -q tests/test_early_exit_diagnostics.py
from __future__ import annotations

import os
import socket
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


class OfflineNetworkError(RuntimeError):
    pass


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    for name in tuple(os.environ):
        if name.startswith(("KIS_", "ALPACA_", "APCA_", "OPENAI_", "ANTHROPIC_")):
            os.environ.pop(name)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    import pytest

    with ExitStack() as guards:
        for target, name in (
            (socket.socket, "connect"), (socket.socket, "connect_ex"),
            (socket, "create_connection"),
        ):
            guards.enter_context(patch.object(
                target, name, side_effect=OfflineNetworkError("network disabled by offline test runner"),
            ))
        return pytest.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
