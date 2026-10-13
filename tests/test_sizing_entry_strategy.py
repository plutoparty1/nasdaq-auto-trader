from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from nasdaq_auto_trader.experimental_exit_models import ExitPolicy
from nasdaq_auto_trader.models import Bar, Position
from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy
from nasdaq_auto_trader.sizing_entry_strategy import BreakoutEntryStrategy
from nasdaq_auto_trader.strategy_config import StrategyConfig


def config(*, sell_score: int = 99) -> StrategyConfig:
    return StrategyConfig(sma_fast=5, sma_slow=20, ema_fast=5, ema_slow=20,
                          long_sma=20, buy_score=99, sell_score=sell_score)


def history() -> list[Bar]:
    start = datetime(2026, 1, 2, 21, tzinfo=UTC)
    bars = [Bar('TEST', (start + timedelta(days=index)).isoformat(),
                10, 10.1, 9.9, 10, 1000) for index in range(70)]
    bars[-1] = replace(bars[-1], close=10.2, high=100, volume=1001)
    return bars


def test_replaces_legacy_buy_score_and_excludes_current_high() -> None:
    # Given a breakout with a legacy score below the configured threshold.
    bars = history()
    baseline = ProfitabilityStrategy(config(), ExitPolicy())
    assert baseline.decide('TEST', bars, None).action == 'hold'
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    # When the completed daily breakout is evaluated.
    result = strategy.decide('TEST', bars, None)
    # Then the new entry does not retain the legacy score gate or today's high.
    assert result.action == 'buy'
    assert not strategy.records[-1].forced
    assert strategy.records[-1].base_action == 'buy'
    assert strategy.records[-1].buy_score is None
    evidence = strategy.breakout_records[-1]
    assert evidence.prior_20_high == 10.1
    assert evidence.sma_50 == pytest.approx(10.004)
    assert evidence.prior_20_average_volume == 1000
    assert evidence.current_volume == 1001
    assert evidence.entry_condition_met


@pytest.mark.parametrize('old_close,current_close,volume', [
    (11, 10.2, 1001), (10, 10.1, 1001), (10, 10.2, 1000),
])
def test_every_comparison_is_strict(old_close: float, current_close: float, volume: float) -> None:
    # Given one equality or failed condition while the other conditions qualify.
    bars = history()
    bars[:49] = [replace(bar, open=old_close, high=old_close + .1,
                         low=old_close - .1, close=old_close) for bar in bars[:49]]
    bars[-1] = replace(bars[-1], close=current_close, volume=volume)
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    # When the conjunction is evaluated.
    result = strategy.decide('TEST', bars, None)
    # Then a failed condition cannot be compensated by other conditions.
    assert result.action == 'hold'
    assert not strategy.records[-1].entry_condition_met


@pytest.mark.parametrize('field,value', [('high', float('nan')), ('open', 0),
                                        ('close', float('inf')), ('volume', -1)])
def test_invalid_required_history_blocks_entry(field: str, value: float) -> None:
    # Given invalid data inside the required lookback.
    bars = history()
    bars[-2] = replace(bars[-2], **{field: value})
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    # When evaluating the candidate.
    result = strategy.decide('TEST', bars, None)
    # Then the failed data requirement cannot become an entry.
    assert result.action == 'hold'
    assert not strategy.breakout_records[-1].data_valid


def test_insufficient_history_blocks_entry() -> None:
    # Given fewer than fifty daily bars.
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    # When evaluating the incomplete indicator history.
    result = strategy.decide('TEST', history()[-49:], None)
    # Then no signal is invented.
    assert result.action == 'hold'
    assert not strategy.breakout_records[-1].data_valid


def test_future_bar_blocks_entry_and_observation_values() -> None:
    # Given a breakout bar that is not yet complete at the observation time.
    bars = history()
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    # When evaluation occurs before the daily completion.
    result = strategy.evaluate('TEST', bars, None, evaluation_timestamp=bars[-2].timestamp)
    # Then neither the decision nor its evidence uses the future values.
    assert result.action == 'hold'
    assert result.reasons == ['completed_bar_unavailable_or_future']
    assert strategy.breakout_records[-1].close is None
    assert not strategy.records[-1].entry_condition_met


def test_duplicate_completed_signal_cannot_reenter() -> None:
    # Given a qualifying bar already evaluated and a finished round trip.
    bars = history()
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    first = strategy.decide('TEST', bars, None)
    strategy.register_entry_fill('TEST', first.latest_price, 1, bars[-1].timestamp)
    strategy.register_exit_fill('TEST', 0)
    # When the same completed bar is reevaluated.
    result = strategy.decide('TEST', bars, None)
    # Then duplicate entry remains blocked.
    assert result.action == 'hold'
    assert result.reasons[-1] == 'completed_bar_already_evaluated'


def test_real_technical_sell_signal_vetoes_breakout() -> None:
    # Given a breakout that also reaches the common technical sell threshold.
    bars = history()
    bars[-1] = replace(bars[-1], high=10.21)
    strategy = BreakoutEntryStrategy(config(sell_score=4), ExitPolicy())
    # When the completed signal is evaluated while flat.
    result = strategy.decide('TEST', bars, None)
    # Then the unchanged collision veto wins.
    assert result.action == 'hold'
    assert result.reasons[-1] == 'conflicting_entry_exit_signal'
    assert strategy.records[-1].entry_condition_met


def test_protection_survives_duplicate_and_future_bar() -> None:
    # Given an existing position whose mark crosses its initial stop.
    bars = history()
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    _ = strategy.decide('TEST', bars, None)
    strategy.register_entry_fill('TEST', 10.2, 1, bars[-1].timestamp)
    held = Position('TEST', 1, 9.2, 10.2)
    # When the duplicated daily bar is ahead of the observation time.
    result = strategy.evaluate('TEST', bars, held, evaluation_timestamp=bars[-2].timestamp)
    # Then entry guards do not disable mark-based protection.
    assert result.action == 'sell'
    assert result.reasons == ['fixed_stop_loss']
    assert strategy.records[-1].protective_evaluation


def test_holding_path_keeps_general_technical_exit() -> None:
    # Given an ordinary technical sell above the wide initial stop.
    bars = [replace(bar, open=10 + (69 - index) * .001,
                    high=10.2, low=9.9, close=10 + (69 - index) * .001)
            for index, bar in enumerate(history())]
    held = Position('TEST', 2, 20, 10.01)
    baseline = ProfitabilityStrategy(config(sell_score=4), ExitPolicy())
    strategy = BreakoutEntryStrategy(config(sell_score=4), ExitPolicy())
    expected = baseline.decide('TEST', bars, held)
    # When the same held position uses P2.
    result = strategy.decide('TEST', bars, held)
    # Then the complete exit decision is identical.
    assert result == expected
    assert result.action == 'sell'
    assert result.score < 88


def test_sma_equality_is_not_an_entry() -> None:
    # Given the fifty closes average exactly ten, with prior highs below ten.
    prices = [10] * 20 + [11] * 20 + [10] * 9 + [9] * 20 + [10]
    bars = [replace(bar, open=price, close=price, low=price - .1, high=price + .1)
            for bar, price in zip(history(), prices, strict=True)]
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    # When close equals the fifty-day simple moving average.
    result = strategy.decide('TEST', bars, None)
    # Then the strict trend condition alone blocks the otherwise valid breakout.
    evidence = strategy.breakout_records[-1]
    assert evidence.close == evidence.sma_50 == 10
    assert evidence.close_above_prior_high and evidence.volume_above_prior_average
    assert result.action == 'hold'


def test_prior_high_window_uses_exactly_twenty_excluded_current_bars() -> None:
    # Given a very high bar twenty-one days ago and ordinary prior twenty highs.
    bars = history()
    bars[-22] = replace(bars[-22], high=200)
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    # When the next completed close breaks only the designated prior twenty days.
    result = strategy.decide('TEST', bars, None)
    # Then both the current and twenty-one-day-old high are excluded.
    assert result.action == 'buy'
    assert strategy.breakout_records[-1].prior_20_high == 10.1


def test_hidden_future_history_cannot_be_used_through_old_completion_id() -> None:
    # Given an explicit old completion id but a future candle in the input list.
    bars = history()
    strategy = BreakoutEntryStrategy(config(), ExitPolicy())
    # When the caller provides a completion id earlier than the last candle.
    result = strategy.evaluate('TEST', bars, None, evaluation_timestamp=bars[-2].timestamp,
                               completed_bar_id=bars[-2].timestamp)
    # Then the entry predicate refuses to read that future candle.
    assert result.action == 'hold'
    assert not strategy.breakout_records[-1].data_valid
    assert strategy.breakout_records[-1].close is None
