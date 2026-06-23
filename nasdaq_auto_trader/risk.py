"""주문 전에 계좌를 보호하는 기본 위험관리 규칙을 담는다."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AccountSnapshot, OrderRequest, Position, TradeDecision


@dataclass(frozen=True)
class RiskConfig:
    """한 종목당 최대 투자 비율과 현금 여유분을 설정한다."""

    max_position_pct: float = 0.10
    min_cash_buffer_pct: float = 0.05
    min_order_notional: float = 50.0
    max_order_notional: float | None = None


class RiskManager:
    """전략 판단을 실제 주문 가능한 크기로 바꾼다."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        """설정이 없으면 기본 위험 제한을 사용한다."""

        self.config = config or RiskConfig()

    def build_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None:
        """매수/매도 판단을 위험 제한이 반영된 주문으로 바꾼다."""

        if decision.action == "hold":
            return None
        if decision.action == "sell":
            return self._sell_order(decision, position)
        return self._buy_order(decision, account, position, latest_price)

    def _buy_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None:
        """계좌 크기와 현금 여유분을 보고 매수 금액을 정한다."""

        current_value = position.market_value if position else 0.0
        target_value = account.equity * self.config.max_position_pct
        remaining_target = max(target_value - current_value, 0.0)
        cash_after_buffer = max(
            account.cash - account.equity * self.config.min_cash_buffer_pct,
            0.0,
        )
        notional = min(remaining_target, cash_after_buffer, account.buying_power)
        if self.config.max_order_notional is not None:
            notional = min(notional, self.config.max_order_notional)
        notional = round(notional, 2)

        if latest_price <= 0 or notional < self.config.min_order_notional:
            return None
        return OrderRequest(symbol=decision.symbol, side="buy", notional=notional)

    def _sell_order(
        self,
        decision: TradeDecision,
        position: Position | None,
    ) -> OrderRequest | None:
        """보유 수량이 있을 때만 전량 매도 주문을 만든다."""

        if position is None or position.qty <= 0:
            return None
        return OrderRequest(symbol=decision.symbol, side="sell", qty=position.qty)
