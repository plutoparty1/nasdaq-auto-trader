from unittest.mock import patch

import pytest

from nasdaq_auto_trader.automatic_buy_receipts import automatic_buy_receipt_block
from nasdaq_auto_trader.brokers.alpaca import AlpacaClient, AlpacaCredentials
from nasdaq_auto_trader.models import OrderRequest, Position
from tests.test_automatic_buy_receipts import submitted_engine
from tests.test_kis_canary_reconciliation import FakeKISClient
from tests.test_kis_history_status import _row


@pytest.mark.parametrize("filled", [0, 1])
def test_real_kis_adapter_releases_completed_cancel_receipt(tmp_path, filled):
    engine, fixture_broker, _market = submitted_engine(tmp_path)
    symbol = fixture_broker.orders[0].symbol
    rows = [
        _row(odno="1", pdno=symbol, ord_dt="20260713", ft_ord_qty="2",
             ft_ccld_qty=str(filled), ft_ccld_unpr3="239" if filled else "0"),
        _row(odno="2", orgn_odno="1", rvse_cncl_dvsn="02", pdno=symbol,
             ord_dt="20260713", ft_ord_qty=str(2 - filled)),
    ]
    engine.broker = FakeKISClient(iter([{"output": rows}]))
    positions = {symbol: Position(symbol, filled, 239 * filled, 239)} if filled else {}

    result = automatic_buy_receipt_block(engine, OrderRequest("MSFT", "buy", qty=1), positions)

    assert result is None
    assert engine.automatic_order_guard.session_store.load_buy_receipts() == ()


@pytest.mark.parametrize("broker_name", ["kis", "alpaca"])
def test_real_adapter_external_sale_releases_receipt(tmp_path, broker_name):
    engine, fixture_broker, _market = submitted_engine(tmp_path)
    symbol = fixture_broker.orders[0].symbol
    if broker_name == "kis":
        rows = [
            _row(odno="1", pdno=symbol, ord_dt="20260713", ord_tmd="103500",
                 ft_ord_qty="2", ft_ccld_qty="2", ft_ccld_unpr3="239"),
            _row(odno="2", pdno=symbol, sll_buy_dvsn_cd="01", ord_dt="20260713",
                 ord_tmd="103600", ft_ord_qty="2", ft_ccld_qty="2", ft_ccld_unpr3="239"),
        ]
        engine.broker = FakeKISClient(iter([{"output": rows}]))
        result = automatic_buy_receipt_block(engine, OrderRequest("MSFT", "buy", qty=1), {})
    else:
        client = AlpacaClient(AlpacaCredentials("test-key", "test-secret"))
        engine.broker = client
        rows = [
            {"id": "2", "symbol": symbol, "side": "sell", "qty": "2", "filled_qty": "2",
             "filled_avg_price": "239", "status": "filled", "submitted_at": "2026-07-13T14:36:00Z"},
            {"id": "1", "symbol": symbol, "side": "buy", "qty": "2", "filled_qty": "2",
             "filled_avg_price": "239", "status": "filled", "submitted_at": "2026-07-13T14:35:00Z"},
        ]
        with patch.object(client, "_request", return_value=rows):
            result = automatic_buy_receipt_block(engine, OrderRequest("MSFT", "buy", qty=1), {})

    assert result is None
    assert engine.automatic_order_guard.session_store.load_buy_receipts() == ()
