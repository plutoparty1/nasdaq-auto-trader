from __future__ import annotations

from pathlib import Path

from nasdaq_auto_trader.live_canary_identity import executable_sha256


def test_source_directory_digest_covers_python_files_deterministically(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    source = package / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    first = executable_sha256(package)

    (package / "ignored.txt").write_text("not executable source", encoding="utf-8")
    assert executable_sha256(package) == first

    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert executable_sha256(package) != first
