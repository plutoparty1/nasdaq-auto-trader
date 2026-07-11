import copy
import unittest
from datetime import date

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.quant_data.universe_snapshot import (
    UniverseSnapshotError,
    load_default_universe,
    parse_universe_snapshot,
    universe_freshness,
)


class AutoSymbolUniverseTests(unittest.TestCase):
    def test_default_snapshot_has_current_official_membership_changes(self):
        snapshot = load_default_universe()
        symbols = {item.symbol for item in snapshot.symbols}

        self.assertEqual(snapshot.universe_id, "nasdaq_100")
        self.assertGreaterEqual(len(symbols), 100)
        self.assertTrue({"ALAB", "CRWV", "NBIS", "RKLB", "TER"} <= symbols)
        self.assertFalse({"CHTR", "CTSH", "INSM", "VRSK", "ZS"} & symbols)

    def test_snapshot_rejects_duplicate_invalid_empty_and_oversized_symbols(self):
        valid = _valid_payload()
        cases = (
            ([], "universe_symbols_empty"),
            ([{"symbol": "AAPL"}, {"symbol": "AAPL"}], "universe_symbol_duplicate"),
            ([{"symbol": "bad symbol"}], "universe_symbol_invalid"),
            ([{"symbol": f"S{index:03d}"} for index in range(121)], "universe_symbols_oversized"),
        )

        for symbols, reason in cases:
            with self.subTest(reason=reason):
                payload = copy.deepcopy(valid)
                payload["symbols"] = symbols
                payload["checksum"] = "ignored"
                with self.assertRaises(UniverseSnapshotError) as raised:
                    parse_universe_snapshot(payload, verify_checksum=False)
                self.assertEqual(raised.exception.reason, reason)

    def test_snapshot_rejects_checksum_and_effective_date_errors(self):
        bad_checksum = _valid_payload()
        bad_checksum["checksum"] = "sha256:deadbeef"
        bad_date = _valid_payload()
        bad_date["effective_date"] = "07/10/2026"

        with self.assertRaises(UniverseSnapshotError) as checksum_error:
            parse_universe_snapshot(bad_checksum)
        with self.assertRaises(UniverseSnapshotError) as date_error:
            parse_universe_snapshot(bad_date, verify_checksum=False)

        self.assertEqual(checksum_error.exception.reason, "universe_checksum_mismatch")
        self.assertEqual(date_error.exception.reason, "universe_effective_date_invalid")

    def test_snapshot_staleness_blocks_live_and_warns_nonlive(self):
        snapshot = parse_universe_snapshot(_valid_payload(), verify_checksum=False)

        live = universe_freshness(snapshot, "live", date(2026, 11, 8))
        paper = universe_freshness(snapshot, "paper", date(2026, 11, 8))

        self.assertEqual(live.blocked_reason, "universe_snapshot_stale")
        self.assertEqual(paper.blocked_reason, "")
        self.assertEqual(paper.warnings, ("universe_snapshot_stale",))


def _valid_payload() -> JsonObject:
    return {
        "schema_version": 1,
        "universe_id": "nasdaq_100",
        "effective_date": "2026-07-10",
        "source_url": "https://api.nasdaq.com/api/quote/list-type/nasdaq100",
        "source_notes": ["test fixture"],
        "symbols": [{"symbol": "AAPL"}, {"symbol": "MSFT"}],
        "checksum": "ignored",
    }


if __name__ == "__main__":
    unittest.main()
