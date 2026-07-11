import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.quant_data.symbol_selector import (
    ResolvedStrategy,
    StrategyResolutionBlock,
    resolve_strategy,
    select_symbols,
)
from nasdaq_auto_trader.quant_data.universe_snapshot import parse_universe_snapshot
from tests.ai_quant_fixtures import bars, promoted_payload, valid_spec_payload


class AutoSymbolSelectorTests(unittest.TestCase):
    def test_promoted_identity_must_match_strategy_spec_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            paths.spec_dir.mkdir(parents=True)
            payload = valid_spec_payload()
            payload["strategy_id"] = "different"
            payload["version"] = "v9"
            (paths.spec_dir / "expected-v1.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            paths.promoted_path.write_text(
                json.dumps(
                    promoted_payload("expected")
                ),
                encoding="utf-8",
            )

            resolution = resolve_strategy("live", paths)

        self.assertIsInstance(resolution, StrategyResolutionBlock)
        self.assertEqual(resolution.reason, "strategy_spec_missing_or_invalid")
    def test_paper_resolver_uses_highest_eligible_score_with_stable_tie(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_spec(paths, "alpha", "v1", 0.1)
            _write_spec(paths, "beta", "v1", 0.1)
            _write_registry(
                paths,
                [
                    _record(("beta", "v1"), "paper_candidate", 0.8),
                    _record(("alpha", "v1"), "paper_candidate", 0.8),
                    _record(("rejected", "v1"), "rejected", 0.99),
                ],
            )

            resolved = resolve_strategy("paper", paths)

        self.assertIsInstance(resolved, ResolvedStrategy)
        self.assertEqual(resolved.spec.strategy_id, "alpha")

    def test_paper_resolver_accepts_validation_passed_learning_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_spec(paths, "learned", "v1", 0.1)
            _write_registry(paths, [_record(("learned", "v1"), "validation_passed", 0.5)])

            resolved = resolve_strategy("paper", paths)

        self.assertIsInstance(resolved, ResolvedStrategy)
        self.assertEqual(resolved.spec.strategy_id, "learned")

    def test_rollback_blocks_even_when_paper_candidate_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_spec(paths, "alpha", "v1", 0.1)
            _write_registry(paths, [_record(("alpha", "v1"), "paper_candidate", 0.8)])
            paths.promoted_path.write_text(
                json.dumps({"status": "rollback", "mode": "no_trade"}),
                encoding="utf-8",
            )

            resolved = resolve_strategy("paper", paths)

        self.assertIsInstance(resolved, StrategyResolutionBlock)
        self.assertEqual(resolved.reason, "promoted_strategy_rollback")

    def test_live_resolver_requires_current_manually_approved_champion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_spec(paths, "alpha", "v1", 0.1)
            promoted = promoted_payload("alpha")
            promoted["manual_approval"] = False
            paths.promoted_path.write_text(json.dumps(promoted), encoding="utf-8")

            blocked = resolve_strategy("live", paths)
            promoted["manual_approval"] = True
            paths.promoted_path.write_text(json.dumps(promoted), encoding="utf-8")
            resolved = resolve_strategy("live", paths)

        self.assertIsInstance(blocked, StrategyResolutionBlock)
        self.assertEqual(blocked.reason, "manual_approval_missing")
        self.assertIsInstance(resolved, ResolvedStrategy)

    def test_complete_selection_report_is_permutation_stable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_spec(paths, "alpha", "v1", 0.1)
            _write_registry(paths, [_record(("alpha", "v1"), "paper_candidate", 0.8)])
            resolved = resolve_strategy("paper", paths)
            if not isinstance(resolved, ResolvedStrategy):
                self.fail(resolved.reason)
            snapshot = _snapshot()

            first = select_symbols(
                snapshot,
                resolved,
                {"MSFT": bars("MSFT"), "AAPL": bars("AAPL")},
            )
            second = select_symbols(
                snapshot,
                resolved,
                {"AAPL": bars("AAPL"), "MSFT": bars("MSFT")},
            )

        self.assertEqual(first, second)
        self.assertEqual(first.selected_symbols, ("MSFT", "AAPL"))
        self.assertEqual(tuple(item.symbol for item in first.ranked), ("MSFT", "AAPL"))

    def test_valid_inputs_below_threshold_return_no_trade(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_spec(paths, "alpha", "v1", 0.99)
            _write_registry(paths, [_record(("alpha", "v1"), "paper_candidate", 0.8)])
            resolved = resolve_strategy("paper", paths)
            if not isinstance(resolved, ResolvedStrategy):
                self.fail(resolved.reason)

            flat_bars = [
                replace(item, open=100, high=101, low=99, close=100)
                for item in bars("AAPL")
            ]
            report = select_symbols(_snapshot(), resolved, {"AAPL": flat_bars})

        self.assertEqual(report.status, "no_trade")
        self.assertEqual(report.selected_symbols, ())


def _write_spec(
    paths: StrategyArtifactPaths,
    strategy_id: str,
    version: str,
    threshold: float,
) -> None:
    payload = valid_spec_payload()
    payload["strategy_id"] = strategy_id
    payload["version"] = version
    payload["entry_rule"]["threshold"] = threshold
    paths.spec_dir.mkdir(parents=True, exist_ok=True)
    (paths.spec_dir / f"{strategy_id}-{version}.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _write_registry(paths: StrategyArtifactPaths, records: list[JsonObject]) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.registry_path.write_text(json.dumps(records), encoding="utf-8")


def _record(
    identity: tuple[str, str],
    status: str,
    score: float,
) -> JsonObject:
    strategy_id, version = identity
    return {
        "strategy_id": strategy_id,
        "version": version,
        "status": status,
        "allowed_for_live": False,
        "manual_approval": False,
        "research_basis": {
            "provider": "insane_search",
            "research_ids": ["research-1"],
            "source_ids": ["source-1"],
            "summary": "fixture",
        },
        "score": score,
        "rejection_reasons": [],
    }


def _snapshot():
    return parse_universe_snapshot(
        {
            "schema_version": 1,
            "universe_id": "nasdaq_100",
            "effective_date": "2026-07-10",
            "source_url": "https://api.nasdaq.com/api/quote/list-type/nasdaq100",
            "source_notes": ["fixture"],
            "symbols": [{"symbol": "MSFT"}, {"symbol": "AAPL"}],
            "checksum": "ignored",
        },
        verify_checksum=False,
    )


if __name__ == "__main__":
    unittest.main()
