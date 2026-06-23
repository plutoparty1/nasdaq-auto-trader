"""과거 CSV 데이터로 전략을 간단히 검증하는 백테스트를 제공한다."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import AccountSnapshot, Bar, Position
from .risk import RiskManager
from .strategy import TechnicalStrategy


@dataclass
class BacktestTrade:
    """백테스트 중 발생한 가상 매매 한 건을 담는다."""

    timestamp: str
    symbol: str
    side: str
    price: float
    qty: float
    notional: float
    reasons: list[str]


@dataclass
class BacktestResult:
    """백테스트 결과 요약과 거래 목록을 담는다."""

    starting_cash: float
    ending_value: float
    trades: list[BacktestTrade] = field(default_factory=list)

    @property
    def return_pct(self) -> float:
        """시작 금액 대비 수익률을 퍼센트로 계산한다."""

        if self.starting_cash == 0:
            return 0.0
        return (self.ending_value - self.starting_cash) / self.starting_cash * 100


class Backtester:
    """전략과 위험관리 규칙을 과거 데이터에 순서대로 적용한다."""

    def __init__(self, strategy: TechnicalStrategy, risk_manager: RiskManager) -> None:
        """백테스트에 쓸 전략과 위험관리 객체를 받는다."""

        self.strategy = strategy
        self.risk_manager = risk_manager

    def run(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        starting_cash: float = 10_000,
    ) -> BacktestResult:
        """각 종목의 봉을 순서대로 읽으며 가상 매매를 수행한다."""

        cash = starting_cash
        positions: dict[str, Position] = {}
        trades: list[BacktestTrade] = []

        for symbol, bars in bars_by_symbol.items():
            for index in range(1, len(bars) + 1):
                window = bars[:index]
                latest = window[-1]
                position = positions.get(symbol)
                equity = cash + self._positions_value(positions, bars_by_symbol, index)
                account = AccountSnapshot(cash=cash, equity=equity, buying_power=cash)
                decision = self.strategy.decide(symbol, window, position)
                order = self.risk_manager.build_order(
                    decision,
                    account,
                    position,
                    latest.close,
                )
                if order is None:
                    continue

                if order.side == "buy" and order.notional is not None:
                    qty = order.notional / latest.close
                    cash -= order.notional
                    positions[symbol] = Position(
                        symbol=symbol,
                        qty=qty,
                        market_value=order.notional,
                        avg_entry_price=latest.close,
                    )
                    trades.append(
                        BacktestTrade(
                            latest.timestamp,
                            symbol,
                            "buy",
                            latest.close,
                            qty,
                            order.notional,
                            decision.reasons,
                        )
                    )

                if order.side == "sell" and position is not None:
                    notional = position.qty * latest.close
                    cash += notional
                    positions.pop(symbol, None)
                    trades.append(
                        BacktestTrade(
                            latest.timestamp,
                            symbol,
                            "sell",
                            latest.close,
                            position.qty,
                            notional,
                            decision.reasons,
                        )
                    )

        ending_value = cash + self._latest_positions_value(positions, bars_by_symbol)
        return BacktestResult(starting_cash, ending_value, trades)

    def _positions_value(
        self,
        positions: dict[str, Position],
        bars_by_symbol: dict[str, list[Bar]],
        index: int,
    ) -> float:
        """현재 순서에서 보유 종목의 가치를 대략 계산한다."""

        total = 0.0
        for symbol, position in positions.items():
            bars = bars_by_symbol[symbol]
            price_index = min(index - 1, len(bars) - 1)
            total += position.qty * bars[price_index].close
        return total

    def _latest_positions_value(
        self,
        positions: dict[str, Position],
        bars_by_symbol: dict[str, list[Bar]],
    ) -> float:
        """마지막 가격으로 보유 종목 가치를 계산한다."""

        total = 0.0
        for symbol, position in positions.items():
            total += position.qty * bars_by_symbol[symbol][-1].close
        return total
