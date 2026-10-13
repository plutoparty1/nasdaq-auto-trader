import json
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.holdout_validation import HOLDOUT_PROTOCOL_VERSION
from nasdaq_auto_trader.ai_quant_lab.operator_models import OperatorPaths
from nasdaq_auto_trader.learning_runner import run_learning_only
from nasdaq_auto_trader.quant_data.symbol_selector import (
    ResolvedStrategy,
    resolve_strategy,
)
from tests.test_holdout_validation import _bars


def _paths(root: Path) -> OperatorPaths:
    return OperatorPaths(root / "config.json", root / "registry.json", root / "promoted.json",
                         root / "specs", root / "audit.jsonl")


def test_real_holdout_registers_paper_candidate_without_live_permission(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    result = run_learning_only(paths, _bars())

    assert result.accepted_candidates == 1
    assert result.submitted_orders == 0
    assert not paths.promoted_path.exists()
    record = json.loads(paths.registry_path.read_text(encoding="utf-8"))[0]
    assert record["status"] == "paper_candidate"
    assert record["allowed_for_live"] is False
    assert record["manual_approval"] is False
    artifacts = StrategyArtifactPaths(tmp_path, paths.registry_path, paths.promoted_path,
                                      paths.spec_dir, paths.audit_log_path, paths.ai_config_path)
    assert isinstance(resolve_strategy("paper", artifacts), ResolvedStrategy)
    assert not isinstance(resolve_strategy("live", artifacts), ResolvedStrategy)
    report_path = next((paths.spec_dir / "reports").glob("*.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["learning_protocol_version"] == HOLDOUT_PROTOCOL_VERSION
    assert report["holdout_evidence"]["passed"] is True
    assert report["holdout_evidence"]["test_bars"] == 126
    assert report["missing_advanced_metrics"]
    assert report["promoted_to_live"] is False


def test_old_rejected_report_is_revalidated_under_new_protocol(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    run_learning_only(paths, _bars())
    report_path = next((paths.spec_dir / "reports").glob("*.json"))
    report_path.write_text('{"evidence_scope":"single_backtest_in_sample"}', encoding="utf-8")
    records = json.loads(paths.registry_path.read_text(encoding="utf-8"))
    records[0]["status"] = "rejected"
    paths.registry_path.write_text(json.dumps(records), encoding="utf-8")

    result = run_learning_only(paths, _bars())

    assert result.accepted_candidates == 1
    assert "data_unchanged" not in result.reasons


def test_same_protocol_and_data_skip_repeated_screen(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    run_learning_only(paths, _bars())
    before = paths.audit_log_path.read_bytes()

    result = run_learning_only(paths, _bars())

    assert result.accepted_candidates == 0
    assert result.reasons == ("data_unchanged",)
    assert paths.audit_log_path.read_bytes() == before


def test_insufficient_history_explains_available_and_required_bars(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    result = run_learning_only(paths, _bars(100))

    assert result.accepted_candidates == 0
    assert "holdout_history_insufficient" in result.reasons
    assert any("100" in line and "306" in line for line in result.data_diagnostics)


def test_audit_failure_report_is_rejected_and_retry_can_recover(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.audit_log_path.mkdir()

    failed = run_learning_only(paths, _bars())

    assert "audit_log_write_failed" in failed.reasons
    report_path = next((paths.spec_dir / "reports").glob("*.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["promotion_decision"] == "rejected"
    assert "audit_log_write_failed" in report["rejection_reasons"]
    paths.audit_log_path.rmdir()
    recovered = run_learning_only(paths, _bars())
    assert recovered.accepted_candidates == 1


def test_changed_cost_policy_revalidates_same_bars(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    run_learning_only(paths, _bars())
    assert paths.ai_config_path is not None
    config = json.loads(paths.ai_config_path.read_text(encoding="utf-8"))
    config["commission_bps"] = 1000
    paths.ai_config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_learning_only(paths, _bars())

    assert "data_unchanged" not in result.reasons
    assert result.accepted_candidates == 0


def test_changed_saved_spec_cannot_reuse_passing_report(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    run_learning_only(paths, _bars())
    spec_path = next(paths.spec_dir.glob("*.json"))
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    payload["entry_rule"]["threshold"] = 0.1
    spec_path.write_text(json.dumps(payload), encoding="utf-8")

    result = run_learning_only(paths, _bars())

    assert "data_unchanged" not in result.reasons
    assert result.accepted_candidates == 1
