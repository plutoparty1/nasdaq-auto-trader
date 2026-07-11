import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.operating_state import OperatingState, OperatingStateStore, RuntimeState, StateTransitionError


class OperatingStateTests(unittest.TestCase):
    def test_runtime_state_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime_state.json"
            state = RuntimeState(OperatingState.PRE_MARKET_CHECK, datetime(2026, 7, 12, tzinfo=timezone.utc), "preflight:2026-07-13", "alpha:v3", 0.02)
            OperatingStateStore(path).save(state)
            recovered = OperatingStateStore(path).load()
        self.assertEqual(recovered, state)

    def test_duplicate_job_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OperatingStateStore(Path(temp_dir) / "runtime_state.json")
            store.save(RuntimeState.idle())
            self.assertTrue(store.claim_job("training:2026-07-10", OperatingState.OFF_HOURS_LEARNING))
            self.assertFalse(store.claim_job("training:2026-07-10", OperatingState.OFF_HOURS_LEARNING))

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime_state.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(StateTransitionError):
                OperatingStateStore(path).load()
