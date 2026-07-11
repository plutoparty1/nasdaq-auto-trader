from __future__ import annotations

import unittest

from tests import config_engine_cli_block_cases
from tests import config_engine_cli_submit_cases
from tests import config_engine_config_cases
from tests import config_engine_gui_backtest_cases
from tests import config_engine_kis_cases
from tests import config_engine_order_gate_cases

_CASE_MODULES = (
    config_engine_config_cases,
    config_engine_kis_cases,
    config_engine_order_gate_cases,
    config_engine_cli_block_cases,
    config_engine_cli_submit_cases,
    config_engine_gui_backtest_cases,
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None):
    suite = unittest.TestSuite()
    for module in _CASE_MODULES:
        suite.addTests(loader.loadTestsFromModule(module))
    return suite
