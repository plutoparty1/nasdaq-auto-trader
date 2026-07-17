from __future__ import annotations

import json

from nasdaq_auto_trader.live_canary_audit import (
    MAX_AUDIT_BYTES,
    BoundedCanaryAuditLog,
    CanaryAuditEvent,
)


def test_audit_writes_date_partitioned_jsonl_and_redacts_secrets(tmp_path) -> None:
    audit = BoundedCanaryAuditLog(tmp_path)
    event = CanaryAuditEvent(
        "2026-07-17",
        "candidate.scan",
        {
            "symbol": "SAFE",
            "access_token": "token-value",
            "message": "KIS_APP_SECRET=secret-value",
        },
    )

    written = audit.append(event)

    path = tmp_path / "live-canary-2026-07-17.jsonl"
    raw = path.read_text(encoding="utf-8")
    record = json.loads(raw)
    assert written is True
    assert record["market_date"] == "2026-07-17"
    assert record["event_type"] == "candidate.scan"
    assert record["fields"]["symbol"] == "SAFE"
    assert "token-value" not in raw
    assert "secret-value" not in raw


def test_audit_redacts_bearer_and_cookie_headers_inside_nested_fields(tmp_path) -> None:
    audit = BoundedCanaryAuditLog(tmp_path)
    event = CanaryAuditEvent(
        "2026-07-17",
        "nested.headers",
        {
            "nested": {
                "message": (
                    "Authorization: Bearer bearer-secret, "
                    "Cookie: session-cookie; theme=dark, "
                    "Set-Cookie: refresh-cookie; Path=/"
                ),
                "items": [
                    {"text": "Set-Cookie: nested-cookie; Secure"},
                ],
            },
        },
    )

    assert audit.append(event) is True

    raw = (tmp_path / "live-canary-2026-07-17.jsonl").read_text(encoding="utf-8")
    assert "bearer-secret" not in raw
    assert "session-cookie" not in raw
    assert "refresh-cookie" not in raw
    assert "nested-cookie" not in raw


def test_audit_rejects_records_that_would_exceed_ten_mib(tmp_path) -> None:
    audit = BoundedCanaryAuditLog(tmp_path)
    path = tmp_path / "live-canary-2026-07-17.jsonl"
    path.write_bytes(b"x" * MAX_AUDIT_BYTES)

    written = audit.append(CanaryAuditEvent("2026-07-17", "too-large", {}))

    assert written is False
    assert path.stat().st_size == MAX_AUDIT_BYTES


def test_audit_prunes_files_older_than_thirty_days(tmp_path) -> None:
    old = tmp_path / "live-canary-2026-06-16.jsonl"
    boundary = tmp_path / "live-canary-2026-06-17.jsonl"
    current = tmp_path / "live-canary-2026-07-17.jsonl"
    old.write_text("old\n", encoding="utf-8")
    boundary.write_text("boundary\n", encoding="utf-8")
    current.write_text("current\n", encoding="utf-8")
    audit = BoundedCanaryAuditLog(tmp_path)

    audit.prune("2026-07-17")

    assert not old.exists()
    assert boundary.exists()
    assert current.exists()
