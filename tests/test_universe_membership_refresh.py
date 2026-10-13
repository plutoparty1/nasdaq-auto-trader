from datetime import date

from nasdaq_auto_trader.quant_data.universe_snapshot import load_default_universe


def test_default_universe_excludes_ea_after_confirmed_trading_suspension() -> None:
    # Given the Nasdaq membership response dated September 9, 2026.
    expected_count = 102

    # When the production resource loader supplies the learning universe.
    snapshot = load_default_universe()

    # Then the complete dated membership excludes the suspended security.
    assert "EA" not in {item.symbol for item in snapshot.symbols}
    assert len(snapshot.symbols) == expected_count
    assert snapshot.effective_date == date(2026, 9, 9)
