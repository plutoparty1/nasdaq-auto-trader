from nasdaq_auto_trader.backtest import Backtester
from nasdaq_auto_trader.backtest_execution import ExecutionBook
from tests.test_entry_fill_exposure import FirstBarBuy, OneShareLimits, bars


class SpecializedBook(ExecutionBook):
    pass


def test_optional_book_binding_preserves_default_results() -> None:
    # Given an existing one-share backtest and an explicitly selected offline book.
    history = {'AAA': bars('AAA', (2, 2, 3))}
    baseline = Backtester(FirstBarBuy(), OneShareLimits()).run(history, 54)
    observed: list[ExecutionBook] = []
    # When the same engine runs through its optional book injection.
    result = Backtester(FirstBarBuy(), OneShareLimits(),
                        execution_book_type=SpecializedBook,
                        on_book_created=observed.append).run(history, 54)
    # Then the callback binds the actual execution state without changing defaults.
    assert len(observed) == 1
    assert isinstance(observed[0], SpecializedBook)
    assert result == baseline
    assert observed[0].trades == list(result.trades)
    assert result.trades[0].timestamp > result.trades[0].signal_timestamp
