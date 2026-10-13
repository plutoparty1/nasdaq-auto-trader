import base64
import json
from pathlib import Path
from typing import BinaryIO

import pytest

from gp5_to_pdf import JSONValue, parse_parts, save_parts


def test_web_option_opens_mobile_site_without_starting_desktop_ui(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import gp5_to_pdf

    opened: list[str] = []

    def open_browser(url: str) -> bool:
        opened.append(url)
        return True

    def unexpected_window() -> None:
        pytest.fail("--web must not create a desktop window")

    monkeypatch.setattr(gp5_to_pdf.sys, "argv", ["gp5_to_pdf.py", "--web"])
    monkeypatch.setattr(gp5_to_pdf.webbrowser, "open", open_browser)
    monkeypatch.setattr(gp5_to_pdf.tk, "Tk", unexpected_window)
    gp5_to_pdf.main()
    assert opened == ["https://plutoparty1.github.io/gp5-pdf-web/"]
    assert capsys.readouterr().out.strip() == opened[0]


def test_parses_every_part_in_order() -> None:
    pdf = b"%PDF-1.4\nexample"
    raw = json.dumps(
        {
            "parts": ["Guitar", "Bass"],
            "partsBin": [
                base64.b64encode(pdf).decode(),
                base64.b64encode(pdf).decode(),
            ],
        }
    )
    assert parse_parts(raw) == [("Guitar", pdf), ("Bass", pdf)]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"parts": [], "partsBin": []},
        {"parts": ["Guitar"], "partsBin": []},
        {"parts": [12], "partsBin": ["JVBERi0="]},
        {"parts": ["Guitar"], "partsBin": [12]},
        {"parts": ["Guitar"], "partsBin": ["invalid!"]},
        {"parts": ["Guitar"], "partsBin": ["aGVsbG8="]},
    ],
)
def test_rejects_malformed_export(payload: JSONValue) -> None:
    with pytest.raises(ValueError):
        _ = parse_parts(json.dumps(payload))


def test_saves_next_to_source_with_safe_unique_names(tmp_path: Path) -> None:
    source = tmp_path / "한글 연습곡.gp5"
    _ = source.write_bytes(b"original GP5")
    pdf = b"%PDF-1.4\nexample"
    parts = [("../기타:solo", pdf), ("../기타:solo", pdf), ("CON", pdf)]
    first = save_parts(source, parts)
    again = save_parts(source, parts)
    assert len(set(first + again)) == 6
    assert all(p.parent == tmp_path and p.suffix == ".pdf" for p in first + again)
    assert all(p.read_bytes() == pdf for p in first + again)
    assert source.read_bytes() == b"original GP5"


def test_failed_write_removes_partial_pdf_and_preserves_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "score.gp5"
    existing = tmp_path / "score_01_Guitar.pdf"
    _ = existing.write_bytes(b"keep me")
    original_open = Path.open

    def failing_open(path: Path, mode: str) -> BinaryIO:
        assert mode == "xb"
        stream = original_open(path, "xb")
        original_write = stream.write

        def fail_write(data: bytes) -> int:
            _ = original_write(data[:10])
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(stream, "write", fail_write)
        return stream

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "open", failing_open)
        with pytest.raises(OSError, match="0개 저장 후 실패"):
            _ = save_parts(source, [("Guitar", b"%PDF-1.4\npartial PDF")])
    assert existing.read_bytes() == b"keep me"
    assert list(tmp_path.glob("*.pdf")) == [existing]
