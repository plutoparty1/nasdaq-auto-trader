from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite

from .config_manager import ai_features_enabled
from .engine_utils import _call_with_optional_refresh
from .models import AccountSnapshot, Bar, Position


class EnginePortfolioMixin:
    def load_portfolio(
        self,
        refresh: bool = False,
    ) -> tuple[AccountSnapshot, dict[str, Position]]:
        """Return the latest account and positions known to the configured broker."""

        return self._load_account(refresh=refresh), self._load_positions(refresh=refresh)

    def _load_recent_bars(self, symbols: list[str] | None = None) -> dict[str, list[Bar]]:
        """Fetch the configured trailing historical bars."""

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.config.lookback_days)
        requested_symbols = symbols or self.config.symbols
        return self.market_data.get_stock_bars(
            requested_symbols,
            self.config.timeframe,
            start.date().isoformat(),
            end.date().isoformat(),
            self.config.bar_limit,
        )

    def _data_symbols(self) -> list[str]:
        if self.trading_settings is None or not ai_features_enabled(self.trading_settings):
            return self.config.symbols
        return self._ai_candidate_tickers()

    def _load_account(self, refresh: bool = False) -> AccountSnapshot:
        """Return injected account state or query the broker."""

        if self._account is not None:
            return self._account
        if hasattr(self.broker, "get_account"):
            return _call_with_optional_refresh(self.broker.get_account, refresh)
        if hasattr(self.market_data, "get_account"):
            return _call_with_optional_refresh(self.market_data.get_account, refresh)
        return AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000)

    def _load_positions(self, refresh: bool = False) -> dict[str, Position]:
        """Return injected position state or query the broker."""

        if self._positions is not None:
            return self._positions
        if hasattr(self.broker, "list_positions"):
            return _call_with_optional_refresh(self.broker.list_positions, refresh)
        if hasattr(self.market_data, "list_positions"):
            return _call_with_optional_refresh(self.market_data.list_positions, refresh)
        return {}

    def _account_for_order(
        self,
        account: AccountSnapshot,
        symbol: str,
        latest_price: float,
    ) -> tuple[AccountSnapshot, JsonObject | None]:
        """Use KIS psamount buying power for symbol-specific buy sizing."""

        if self.config.broker != "kis" or not hasattr(
            self.market_data,
            "get_overseas_buying_power",
        ):
            return account, None

        raw_buying_power = self.market_data.get_overseas_buying_power(symbol, latest_price)
        buying_power = raw_buying_power if isfinite(raw_buying_power) else 0.0
        buying_power = max(buying_power, 0.0)
        deposited_cash = account.cash if isfinite(account.cash) else 0.0
        deposited_cash = max(deposited_cash, 0.0)
        effective_account = AccountSnapshot(
            cash=min(deposited_cash, buying_power),
            equity=account.equity if account.equity > 0 else buying_power,
            buying_power=buying_power,
        )
        return effective_account, {
            "source": "kis_inquire_psamount",
            "symbol": symbol,
            "latest_price": latest_price,
            "available_amount": buying_power,
            "deposited_cash_ceiling": effective_account.cash,
            "one_share_required": latest_price,
            "one_share_affordable": (
                latest_price > 0
                and effective_account.cash >= latest_price
                and buying_power >= latest_price
            ),
        }
