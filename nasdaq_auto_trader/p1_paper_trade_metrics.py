from __future__ import annotations

from typing import TYPE_CHECKING

from .ai_quant_lab.types import JsonObject, JsonValue
from .backtest_types import BacktestResult, BacktestTrade

if TYPE_CHECKING:
    from .p1_paper_account import PaperAccount


def trade_diagnostics(account: PaperAccount, result: BacktestResult) -> JsonObject:
    entries = {(item.symbol, item.signal_timestamp): item for item in account.entry_risks}
    open_trades: dict[str, tuple[BacktestTrade, list[BacktestTrade]]] = {}
    groups: list[tuple[BacktestTrade, list[BacktestTrade]]] = []
    for trade in result.trades:
        if trade.side == 'buy':
            group: tuple[BacktestTrade, list[BacktestTrade]] = (trade, [])
            open_trades[trade.symbol] = group
            groups.append(group)
        else:
            open_trades[trade.symbol][1].append(trade)
    positions = {position.symbol: position for position in result.ending_positions}
    rows: list[JsonValue] = []
    closed_losses: list[float] = []
    loss_percentages: list[float] = []
    exceed_count = unknown_risk_count = 0
    for buy, sells in groups:
        risk = entries.get((buy.symbol, buy.signal_timestamp))
        remaining = buy.qty - sum(sell.qty for sell in sells)
        complete = remaining <= 1e-10
        realized = sum(sell.pnl for sell in sells)
        unallocated_fee = buy.fee - sum(sell.allocated_entry_fee for sell in sells)
        unrealized = 0.0
        if not complete:
            position = positions[buy.symbol]
            unrealized = position.market_value - remaining * buy.price - unallocated_fee
        net = realized + unrealized
        actual_fees = buy.fee + sum(sell.fee for sell in sells)
        impact = buy.execution_cost + sum(sell.execution_cost for sell in sells)
        loss = max(-realized, 0.0) if complete else None
        pct = 100 * loss / risk.equity if loss is not None and risk is not None and risk.equity > 0 else None
        exceed = loss > risk.planned_risk + 1e-10 if loss is not None and risk is not None else None
        if complete:
            closed_losses.append(loss or 0.0)
            if pct is not None:
                loss_percentages.append(pct)
            unknown_risk_count += risk is None
            exceed_count += exceed is True
        signal_price = risk.price if risk is not None else None
        stop = risk.initial_stop if risk is not None else None
        stop_distance = buy.qty * (signal_price - stop) if signal_price is not None and stop is not None else None
        beyond_stop = sum(sell.qty * max(stop - (sell.price + sell.execution_cost / sell.qty), 0)
                          for sell in sells) if stop is not None else None
        reference_price_loss = sum(sell.qty * (buy.price - buy.execution_cost / buy.qty
                                               - sell.price - sell.execution_cost / sell.qty)
                                   for sell in sells)
        rows.append({
            'symbol': buy.symbol, 'signal_timestamp': buy.signal_timestamp,
            'entry_timestamp': buy.timestamp, 'exit_timestamp': sells[-1].timestamp if complete else None,
            'completed': complete, 'quantity': buy.qty, 'remaining_quantity': max(remaining, 0.0),
            'net_pnl_usd': net, 'realized_pnl_usd': realized,
            'unrealized_pnl_after_entry_fee_usd': unrealized,
            'account_return_contribution_pct': 100 * net / result.starting_cash,
            'entry_signal_equity_usd': risk.equity if risk is not None else None,
            'closed_loss_usd': loss, 'closed_loss_pct_of_entry_signal_equity': pct,
            'planned_risk_usd': risk.planned_risk if risk is not None else None,
            'planned_risk_exceeded': exceed, 'planned_stop_distance_usd': stop_distance,
            'planned_risk_excess_usd': max(loss - risk.planned_risk, 0)
            if loss is not None and risk is not None else None,
            'expected_fees_usd': risk.expected_buy_fee + risk.expected_stop_sell_fee if risk is not None else None,
            'expected_execution_impact_usd': risk.expected_adverse_cost if risk is not None else None,
            'actual_fees_usd': actual_fees, 'actual_execution_impact_usd': impact,
            'execution_impact_treatment': 'embedded_in_fill_prices_not_subtracted_again',
            'reference_price_loss_usd': reference_price_loss if complete else None,
            'price_beyond_initial_stop_usd': beyond_stop,
            'stop_to_exit_reference_move_usd': sum(
                sell.qty * (stop - sell.price) - sell.execution_cost for sell in sells)
            if stop is not None else None,
            'signal_to_entry_reference_move_usd': buy.qty * (
                buy.price - buy.execution_cost / buy.qty - signal_price) if signal_price is not None else None,
            'loss_reconciliation_usd': reference_price_loss + actual_fees + impact if complete else None,
            'delay_attributable_loss_usd': None,
            'delay_attribution': 'not_identifiable_from_daily_ohlc_and_modelled_fills',
            'commission_charge_count': int(buy.fee > 0) + sum(sell.fee > 0 for sell in sells),
            'execution_impact_charge_count': int(buy.execution_cost > 0) + sum(sell.execution_cost > 0 for sell in sells),
        })
    return {
        'trade_contributions': rows, 'maximum_closed_trade_loss_usd': max(closed_losses, default=0.0),
        'maximum_closed_trade_loss_pct_of_entry_signal_equity': (
            max(loss_percentages, default=0.0) if not unknown_risk_count else None),
        'planned_risk_exceed_count': exceed_count,
        'closed_trades_with_unknown_entry_risk': unknown_risk_count,
        'commission_charge_count': sum(trade.fee > 0 for trade in result.trades),
        'execution_impact_charge_count': sum(trade.execution_cost > 0 for trade in result.trades),
    }
