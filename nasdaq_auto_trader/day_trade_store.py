from __future__ import annotations

import json
from pathlib import Path

from .day_trade_types import JsonObject


class OrderRecordStore:
    """Append-only JSONL record store for dry-run and live order decisions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: JsonObject) -> None:
        """Append one order-decision record."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def has_live_buy_today(self, market_date: str) -> bool:
        """Return whether a live buy was already submitted for this market date."""

        for record in self._records():
            if (
                record.get("market_date") == market_date
                and record.get("action") == "buy"
                and record.get("submitted_order") is True
                and record.get("dry_run") is False
                and record.get("live_trading") is True
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
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
        return records
