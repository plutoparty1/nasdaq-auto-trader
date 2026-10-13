from nasdaq_auto_trader import production_replay
from pathlib import Path
import json

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.safe_launcher import load_effective_runtime


def test_isolated_replay_entrypoint_exists():
    # Given the formal executable exposes the isolated full-chain proof.
    # When its replay entrypoint is inspected.
    # Then it accepts a typed runtime, rather than injecting a strategy decision.
    assert callable(getattr(production_replay, "run_replay", None))


def test_real_automatic_selector_reaches_fake_kis_once(tmp_path: Path):
    # Given unchanged pinned strategy and isolated credentials and approvals.
    app = Path("deploy-safe/operating-transition-20261013/NasdaqAutoTrader")
    effective = load_effective_runtime(app)
    runtime = production_replay.ReplayRuntime(effective.config, effective.settings,
        StrategyArtifactPaths.from_root(app / "simulation/NasdaqAutoTrader/ai_quant_lab"),
        app / "NasdaqAutoTraderSafe.exe")
    # When market bars traverse the automatic production engine.
    production_replay.run_replay(tmp_path / "proof.json", runtime)
    # Then one valid signal reaches the real KIS serializer and fake wire once.
    payload = json.loads((tmp_path / "proof.json").read_text(encoding="utf-8"))
    assert len(payload["cases"]["valid"]["fake_kis_requests"]) == 1
    candidate = payload["cases"]["integer_quantity_candidate"]
    assert candidate["cases"]["valid"]["results"][0]["order"]["qty"] == 5
    assert candidate["cases"]["small_account"]["fake_kis_requests"] == []
