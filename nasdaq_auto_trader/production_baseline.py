from __future__ import annotations

import json
import math
import os
from datetime import date, datetime
from pathlib import Path

from .ai_quant_lab.types import JsonValue
from .config_settings import TradingSessionState
from .market_hours import EASTERN
from .models import AccountSnapshot


class ProductionBaselineStore:
    def __init__(self, path: Path, account_digest: str) -> None:
        self.path = path
        self.account_digest = account_digest

    def restore(
        self, state: TradingSessionState, account: AccountSnapshot, now: datetime,
    ) -> str:
        market_date = now.astimezone(EASTERN).date().isoformat()
        state.reset_if_new_day(now)
        payload: JsonValue = None
        try:
            if self.path.exists():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "production_daily_baseline_corrupt"
        if self.path.exists():
            if not isinstance(payload, dict):
                return "production_daily_baseline_corrupt"
            equity = payload.get("starting_equity")
            recorded_date = payload.get("market_date")
            if (payload.get("account_digest") != self.account_digest
                or not isinstance(equity, int | float) or isinstance(equity, bool)
                or not math.isfinite(equity) or equity <= 0 or not isinstance(recorded_date, str)):
                return "production_daily_baseline_corrupt"
            try:
                if date.fromisoformat(recorded_date) > date.fromisoformat(market_date):
                    return "production_daily_baseline_corrupt"
            except ValueError:
                return "production_daily_baseline_corrupt"
            if recorded_date == market_date:
                state.starting_equity = float(equity)
                state.daily_loss_state_unavailable = False
                return ""
        if state.daily_loss_state_unavailable or state.daily_loss_breached:
            return "daily_loss_state_unavailable"
        if not math.isfinite(account.equity) or account.equity <= 0:
            return "production_daily_baseline_invalid"
        state.observe_account(account, now)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as output:
                json.dump({"account_digest": self.account_digest, "market_date": market_date,
                           "starting_equity": state.starting_equity}, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        except OSError:
            return "production_daily_baseline_write_failed"
        return ""
