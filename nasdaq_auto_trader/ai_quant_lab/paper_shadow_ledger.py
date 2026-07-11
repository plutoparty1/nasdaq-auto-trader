from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent, NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject


class LedgerResult(Protocol):
    strategy_id: str
    strategy_version: str
    mode: str
    status: str
    net_pnl: float

    def to_json_object(self) -> JsonObject: ...


class PaperShadowLedger:
    def __init__(self, path: str | Path, audit_logger: NullAuditLogger | None = None) -> None:
        self.path = Path(path)
        self.audit_logger = audit_logger or NullAuditLogger()

    def append(self, result: LedgerResult) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(result.to_json_object(), sort_keys=True) + "\n")
        except OSError:
            return False
        return self.audit_logger.append(
            AuditEvent(
                f"{result.mode}_result_recorded",
                strategy_id=result.strategy_id,
                strategy_version=result.strategy_version,
                payload={"status": result.status, "net_pnl": result.net_pnl},
            )
        )
