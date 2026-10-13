"""Offline user-facing preparation and checkpoint boundary regressions."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


def test_paper_manual_surface_exists() -> None:
    # Given the existing comparison CLI, when paper mode is prepared, then it has a one-shot facade.
    assert importlib.util.find_spec('nasdaq_auto_trader.p1_paper_cli') is not None


def test_checkpoint_preserves_previous_and_detects_corruption(tmp_path: Path) -> None:
    import pytest

    from nasdaq_auto_trader.exit_experiment_config import ExperimentInputError
    from nasdaq_auto_trader.p1_paper_store import read_checkpoint, write_checkpoint
    # Given an immutable first account checkpoint.
    first = write_checkpoint(tmp_path, {'schema_version': 1, 'cash': 54.0}, None)
    original = (tmp_path / first).read_bytes()
    # When the account is advanced and the latest checkpoint is later damaged.
    second = write_checkpoint(tmp_path, {'schema_version': 1, 'cash': 50.0}, first)
    assert read_checkpoint(tmp_path)[1]['cash'] == 50.0
    _ = (tmp_path / second).write_text('{}', encoding='utf-8')
    # Then corruption fails closed and the prior checkpoint remains unchanged.
    with pytest.raises(ExperimentInputError, match='hash_mismatch'):
        _ = read_checkpoint(tmp_path)
    assert (tmp_path / first).read_bytes() == original


def test_interrupted_checkpoint_publication_keeps_previous(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import pytest

    from nasdaq_auto_trader import p1_paper_store as store
    # Given a durable prior snapshot, a crash before pointer publication must not expose new balances.
    first = store.write_checkpoint(tmp_path, {'schema_version': 1, 'cash': 54.0}, None)
    original_replace = os.replace
    def fail_publish(_source: str | Path, _destination: str | Path) -> None:
        raise OSError('synthetic interruption before atomic publication')
    monkeypatch.setattr(os, 'replace', fail_publish)
    with pytest.raises(OSError, match='synthetic interruption'):
        _ = store.write_checkpoint(tmp_path, {'schema_version': 1, 'cash': 50.0}, first)
    assert store.read_checkpoint(tmp_path)[1]['cash'] == 54.0
    monkeypatch.setattr(os, 'replace', original_replace)
    second = store.write_checkpoint(tmp_path, {'schema_version': 1, 'cash': 50.0}, first)
    assert store.read_checkpoint(tmp_path)[0] == second
    assert len(list(tmp_path.glob('checkpoint-*.json'))) == 2
