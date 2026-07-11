from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExpectedExecution:
    strategy_id: str
    symbol: str
    side: str
    qty: int
    expected_price: float


@dataclass(frozen=True, slots=True)
class ActualExecution:
    strategy_id: str
    symbol: str
    side: str
    qty: int
    fill_price: float
    commission: float
    status: str


@dataclass(frozen=True, slots=True)
class PostTradeFeedback:
    expected_orders: int
    actual_orders: int
    failed_orders: int
    average_slippage_bps: float
    total_commission: float
    failure_reasons: tuple[str, ...]

    def to_prompt_feedback(self) -> str:
        return (
            f"expected_orders={self.expected_orders}; actual_orders={self.actual_orders}; "
            f"failed_orders={self.failed_orders}; "
            f"average_slippage_bps={self.average_slippage_bps:.2f}; "
            f"total_commission={self.total_commission:.4f}; "
            f"failure_reasons={','.join(self.failure_reasons)}"
        )


def analyze_post_trade_feedback(
    expected: tuple[ExpectedExecution, ...],
    actual: tuple[ActualExecution, ...],
) -> PostTradeFeedback:
    actual_by_key = {
        (item.strategy_id, item.symbol, item.side): item
        for item in actual
    }
    slips: list[float] = []
    failures = 0
    for item in expected:
        if item.side not in ("buy", "sell"):
            failures += 1
            continue
        execution = actual_by_key.get((item.strategy_id, item.symbol, item.side))
        if execution is None or execution.status != "filled" or execution.qty < item.qty:
            failures += 1
            continue
        slips.append(_slippage_bps(item.side, item.expected_price, execution.fill_price))
    reasons = ("execution_failures_detected",) if failures else ()
    return PostTradeFeedback(
        expected_orders=len(expected),
        actual_orders=len(actual),
        failed_orders=failures,
        average_slippage_bps=sum(slips) / len(slips) if slips else 0.0,
        total_commission=sum(item.commission for item in actual),
        failure_reasons=reasons,
    )


def _slippage_bps(side: str, expected_price: float, fill_price: float) -> float:
    if expected_price <= 0:
        return 0.0
    raw = (fill_price / expected_price - 1) * 10_000
    return raw if side == "buy" else -raw
