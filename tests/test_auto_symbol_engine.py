import json
import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.ai_quant_fixtures import valid_spec_payload
from tests.config_engine_fixtures import compact_strategy_config


class AutoSymbolEngineTests(unittest.TestCase):
    def test_auto_cycle_never_reads_manual_ticker_and_evaluates_held_symbol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_paper_strategy(paths)
            market = _AutoMarketData(
                positions={
                    "HELD": Position("HELD", 1, 100, 100),
                }
            )
            broker = _AcceptedBroker()
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    symbols=["POISON"],
                    strategy=compact_strategy_config(),
                ),
                broker=broker,
                market_data=market,
                trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
                strategy_artifact_paths=paths,
                automatic_order_guard=_guard(paths, Path(temp_dir)),
            )

            results = engine.run_once()

        requested = {symbol for call in market.bar_requests for symbol in call}
        self.assertNotIn("POISON", requested)
        self.assertIn("HELD", requested)
        self.assertIsNotNone(engine.last_selection_report)
        self.assertTrue(any(item["symbol"] == "HELD" for item in results))

    def test_missing_strategy_blocks_before_market_or_broker_and_never_falls_back(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            market = _AutoMarketData()
            broker = _AcceptedBroker()
            engine = TradingEngine(
                AppConfig(mode="dry_run", symbols=["POISON"]),
                broker=broker,
                market_data=market,
                trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
                strategy_artifact_paths=paths,
                automatic_order_guard=_guard(paths, Path(temp_dir)),
            )

            results = engine.run_once()

        self.assertEqual(results, [])
        self.assertEqual(market.bar_requests, [])
        self.assertEqual(broker.orders, [])
        self.assertEqual(engine.last_selection_report.status, "blocked")
        self.assertEqual(
            engine.last_selection_report.blocked_reasons,
            ("eligible_strategy_unavailable",),
        )

    def test_multiple_auto_buys_reserve_cycle_start_cash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_paper_strategy(paths, top_n=2)
            market = _AutoMarketData(account=AccountSnapshot(1000, 1000, 1000))
            broker = _AcceptedBroker()
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    symbols=["POISON"],
                    strategy=compact_strategy_config(),
                    risk=RiskConfig(
                        max_position_pct=0.6,
                        min_cash_buffer_pct=0.05,
                        min_order_notional=1,
                        risk_per_trade_pct=0,
                    ),
                ),
                broker=broker,
                market_data=market,
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    max_daily_buy_count=10,
                    max_position_qty=10,
                ),
                strategy_artifact_paths=paths,
                automatic_order_guard=_guard(paths, Path(temp_dir)),
            )

            results = engine.run_once()

        orders = [item["order"] for item in results if item["order"] is not None]
        buy_notional = sum(order.notional or 0 for order in orders if order.side == "buy")
        self.assertGreaterEqual(len(orders), 2)
        self.assertLessEqual(buy_notional, 950)
        self.assertEqual(broker.orders, [])


class _AutoMarketData:
    def __init__(
        self,
        account: AccountSnapshot | None = None,
        positions: dict[str, Position] | None = None,
        missing_quote_symbol: str = "",
    ) -> None:
        self.account = account or AccountSnapshot(10_000, 10_000, 10_000)
        self.positions = positions or {}
        self.bar_requests: list[list[str]] = []
        self.missing_quote_symbol = missing_quote_symbol
        self.quote_calls = 0

    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        del timeframe, start, end, limit
        self.bar_requests.append(list(symbols))
        return {symbol: _rising_bars(symbol) for symbol in symbols}

    def get_latest_quotes(self, symbols):
        self.quote_calls += 1
        return {
            symbol: {"bp": 199.99, "ap": 200.01}
            for symbol in symbols
            if symbol != self.missing_quote_symbol
        }

    def get_account(self, refresh=False):
        del refresh
        return self.account

    def list_positions(self, refresh=False):
        del refresh
        return self.positions


class _AcceptedBroker:
    def __init__(self) -> None:
        self.orders = []

    def submit_order(self, order):
        self.orders.append(order)
        return {"status": "accepted", "id": str(len(self.orders))}


def _rising_bars(symbol: str) -> list[Bar]:
    return [
        Bar(
            symbol=symbol,
            timestamp="2026-07-10T16:00:00+00:00",
            open=100 + index - 0.5,
            high=100 + index + 1,
            low=100 + index - 1,
            close=100 + index,
            volume=1_000_000,
        )
        for index in range(140)
    ]


def _write_paper_strategy(paths: StrategyArtifactPaths, top_n: int = 2) -> None:
    payload = valid_spec_payload()
    payload["strategy_id"] = "auto"
    payload["entry_rule"]["top_n"] = top_n
    paths.spec_dir.mkdir(parents=True, exist_ok=True)
    (paths.spec_dir / "auto-v1.json").write_text(json.dumps(payload), encoding="utf-8")
    paths.registry_path.write_text(
        json.dumps(
            [
                {
                    "strategy_id": "auto",
                    "version": "v1",
                    "status": "paper_candidate",
                    "allowed_for_live": False,
                    "manual_approval": False,
                    "research_basis": {
                        "provider": "insane_search",
                        "research_ids": ["research-1"],
                        "source_ids": ["source-1"],
                        "summary": "fixture",
                    },
                    "score": 0.9,
                    "rejection_reasons": [],
                }
            ]
        ),
        encoding="utf-8",
    )


def _guard(paths: StrategyArtifactPaths, root: Path) -> AutomaticOrderGuard:
    return AutomaticOrderGuard(
        paths,
        TradingSessionStore(root / "session.json"),
        NullAuditLogger(),
    )


if __name__ == "__main__":
    unittest.main()
