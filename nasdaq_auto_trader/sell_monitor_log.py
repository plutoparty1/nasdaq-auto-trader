from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .sell_monitor_types import JsonObject, SellMonitorSafetyError


class SellMonitorLog:
    """Append-only JSONL log for sell monitor decisions and order outcomes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: JsonObject) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **record}
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())

    def has_unresolved_sell(self, symbol: str) -> bool:
        pending = False
        for record in self._records():
            if (
                record.get("symbol") != symbol
                or record.get("side") != "sell"
                or record.get("dry_run") is True
            ):
                continue
            if record.get("event") in {"sell_order_attempt", "sell_order_error"}:
                pending = True
            elif record.get("event") == "sell_order_submitted":
                pending = False
        return pending

    def has_submitted_sell_today(self, symbol: str, market_date: str) -> bool:
        for record in self._records():
            if (
                record.get("market_date") == market_date
                and record.get("symbol") == symbol
                and record.get("side") == "sell"
                and record.get("submitted_order") is True
            ):
                return True
        return False

    def _records(self) -> list[JsonObject]:
        if not self.path.exists():
            return []
        records: list[JsonObject] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise SellMonitorSafetyError("sell log requires reconciliation") from error
            if not isinstance(record, dict):
                raise SellMonitorSafetyError("sell log requires reconciliation")
            records.append(record)
        return records
