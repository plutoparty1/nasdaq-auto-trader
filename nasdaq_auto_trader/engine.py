"""전략, 시세, 브로커, 위험관리를 이어 붙여 한 번 실행한다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from .broker import AlpacaClient, AlpacaCredentials, DryRunBroker
from .config import AppConfig, validate_trading_mode
from .models import AccountSnapshot, Bar, OrderRequest, Position, TradeDecision
from .risk import RiskManager
from .strategy import TechnicalStrategy


class BrokerLike(Protocol):
    """실제 브로커와 dry-run 브로커가 지켜야 하는 작은 약속이다."""

    def submit_order(self, order: OrderRequest) -> dict:
        """주문 하나를 제출한다."""


class MarketDataLike(Protocol):
    """시세 제공자가 지켜야 하는 작은 약속이다."""

    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        """종목별 봉 데이터를 가져온다."""


class TradingEngine:
    """한 번 실행할 때 시세 조회부터 주문 제출까지 처리한다."""

    def __init__(
        self,
        config: AppConfig,
        broker: BrokerLike | None = None,
        market_data: MarketDataLike | None = None,
        account: AccountSnapshot | None = None,
        positions: dict[str, Position] | None = None,
    ) -> None:
        """테스트에서는 가짜 브로커와 가짜 시세를 넣을 수 있게 한다."""

        validate_trading_mode(config)
        self.config = config
        self.strategy = TechnicalStrategy(config.strategy)
        self.risk_manager = RiskManager(config.risk)
        self._account = account
        self._positions = positions

        alpaca_client: AlpacaClient | None = None
        if broker is None or market_data is None:
            credentials = AlpacaCredentials(
                config.alpaca.api_key,
                config.alpaca.secret_key,
                paper=config.mode != "live",
                feed=config.alpaca.feed,
                timeout=config.alpaca.timeout,
            )
            alpaca_client = AlpacaClient(credentials)

        self.broker = broker or (
            DryRunBroker() if config.mode == "dry_run" else alpaca_client
        )
        self.market_data = market_data or alpaca_client

    def run_once(self) -> list[dict]:
        """현재 설정으로 모든 종목을 한 번 검사하고 필요한 주문을 보낸다."""

        bars_by_symbol = self._load_recent_bars()
        account = self._load_account()
        positions = self._load_positions()
        results: list[dict] = []

        for symbol in self.config.symbols:
            bars = bars_by_symbol.get(symbol, [])
            position = positions.get(symbol)
            decision = self.strategy.decide(symbol, bars, position)
            latest_price = decision.latest_price
            order = self.risk_manager.build_order(
                decision,
                account,
                position,
                latest_price,
            )

            response = None
            if order is not None:
                response = self.broker.submit_order(order)

            results.append(
                {
                    "symbol": symbol,
                    "decision": decision,
                    "order": order,
                    "response": response,
                }
            )
        return results

    def _load_recent_bars(self) -> dict[str, list[Bar]]:
        """설정된 기간만큼 최근 봉 데이터를 가져온다."""

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.config.lookback_days)
        return self.market_data.get_stock_bars(
            self.config.symbols,
            self.config.timeframe,
            start.date().isoformat(),
            end.date().isoformat(),
            self.config.bar_limit,
        )

    def _load_account(self) -> AccountSnapshot:
        """테스트 계좌가 없으면 브로커 계좌를 조회한다."""

        if self._account is not None:
            return self._account
        if hasattr(self.broker, "get_account"):
            return self.broker.get_account()
        return AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000)

    def _load_positions(self) -> dict[str, Position]:
        """테스트 포지션이 없으면 브로커 포지션을 조회한다."""

        if self._positions is not None:
            return self._positions
        if hasattr(self.broker, "list_positions"):
            return self.broker.list_positions()
        return {}


def decision_to_dict(decision: TradeDecision) -> dict:
    """CLI 출력용으로 판단 결과를 딕셔너리로 바꾼다."""

    return {
        "symbol": decision.symbol,
        "action": decision.action,
        "score": decision.score,
        "latest_price": decision.latest_price,
        "reasons": decision.reasons,
    }
