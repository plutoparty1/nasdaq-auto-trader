from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .session_claims import ClaimRecord, ClaimStatus
from .session_safety_reservation import PersistedSafetyState
from .session_state_codec import parse_claims, parse_safety_state


class SessionPayloadError(RuntimeError):
    pass


def read_session_payload(
    path: Path,
) -> tuple[PersistedSafetyState, dict[str, ClaimRecord]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SessionPayloadError("session_store_corrupt")
    raw_safety = payload.get("safety")
    raw_claims = payload.get("claims")
    if not isinstance(raw_safety, dict) or not isinstance(raw_claims, dict):
        raise SessionPayloadError("session_store_corrupt")
    parsed = parse_safety_state(raw_safety)
    safety = PersistedSafetyState(
        market_date=parsed.market_date,
        buy_count=parsed.buy_count,
        sell_count=parsed.sell_count,
        last_order_at=parsed.last_order_at,
        daily_loss_breached=parsed.daily_loss_breached,
        baseline_observed=parsed.baseline_observed,
        position_high_water=parsed.position_high_water,
        closed_position_symbols=parsed.closed_position_symbols,
        position_state_versions=parsed.position_state_versions,
    )
    claims = {
        digest: ClaimRecord(
            ClaimStatus(status),
            market_date or safety.market_date,
        )
        for digest, (status, market_date) in parse_claims(raw_claims).items()
    }
    return safety, claims


def write_session_payload(
    path: Path,
    safety: PersistedSafetyState,
    claims: dict[str, ClaimRecord],
) -> None:
    payload = {
        "schema_version": 1,
        "safety": asdict(safety),
        "claims": {
            digest: {
                "status": record.status.value,
                "market_date": record.market_date,
            }
            for digest, record in claims.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, sort_keys=True)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
