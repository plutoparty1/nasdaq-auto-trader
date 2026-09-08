from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from nasdaq_auto_trader.brokers.kis_client import KISCredentials
from nasdaq_auto_trader.brokers.kis_reconciliation import (
    KISCancelOrder,
    KISCancelResult,
    KISOpenOrder,
    KISOrderHistory,
)
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.live_canary_identity import (
    account_fingerprint,
    executable_sha256,
)
from nasdaq_auto_trader.live_canary_lease import BrokerLiveLease
from nasdaq_auto_trader.live_canary_paths import CanaryPaths
from nasdaq_auto_trader.live_canary_policy import CANARY_POLICY
from nasdaq_auto_trader.live_canary_state import (
    CanaryState,
    CanaryStateStore,
    StateMode,
)
from nasdaq_auto_trader.market_hours import MarketSession
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position


NOW = datetime(2026, 7, 17, 14, 0, tzinfo=UTC)
SESSION = MarketSession(
    True,
    "regular_market_open",
    NOW.isoformat(),
    "2026-07-17T09:30:00-04:00",
    "2026-07-17T16:00:00-04:00",
)


class FakeKIS:
    def __init__(
        self,
        positions: dict[str, Position],
        open_orders: tuple[KISOpenOrder, ...] = (),
        submit_response: dict[str, dict[str, str]] | None = None,
        history: tuple[KISOrderHistory, ...] = (),
        latest_price: float = 19.0,
    ) -> None:
        self.positions = positions
        self.open_orders = open_orders
        self.submit_response = submit_response
        self.history = history
        self.posts = 0
        self.cancels: list[KISCancelOrder] = []
        self.leases: list[BrokerLiveLease] = []
        self.universe_seen: set[str] = set()
        self.latest_price = latest_price
        self.submitted_orders: list[OrderRequest] = []

    def bind_live_lease(self, lease: BrokerLiveLease) -> None:
        self.leases.append(lease)

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        return AccountSnapshot(25.0, 25.0, 25.0)

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        return self.positions

    @contextmanager
    def reconciliation_window(self, deadline_seconds: float) -> Iterator[None]:
        del deadline_seconds
        yield

    def list_open_orders(self) -> tuple[KISOpenOrder, ...]:
        return self.open_orders

    def list_order_history(
        self,
        start_date: str,
        end_date: str,
    ) -> tuple[KISOrderHistory, ...]:
        return self.history

    def get_trade_volume_universe(self, universe: set[str]) -> tuple[str, ...]:
        self.universe_seen = set(universe)
        return ("WBD",) if "WBD" in universe else ()

    def get_price_detail(self, symbol: str) -> dict[str, float]:
        return {"last": 19.0, "volume": 600_000.0}

    def get_best_quote(self, symbol: str) -> dict[str, float]:
        return {"bid": 18.95, "ask": 19.0, "vbid1": 500.0, "vask1": 500.0}

    def get_overseas_buying_power(self, symbol: str, order_price: float) -> float:
        return 25.0

    def get_latest_price(self, symbol: str) -> float:
        return self.latest_price

    def submit_order(self, order: OrderRequest) -> dict[str, dict[str, str]]:
        self.posts += 1
        self.submitted_orders.append(order)
        return self.submit_response or {"output": {"ODNO": "buy-1"}}

    def cancel_order(self, order: KISCancelOrder) -> KISCancelResult:
        self.cancels.append(order)
        return KISCancelResult(order.order_id)


def armed_canary(tmp_path: Path) -> tuple[CanaryPaths, AppConfig, Path]:
    executable = tmp_path / "runner.exe"
    executable.write_bytes(b"runner")
    credentials = KISCredentials("app", "secret", "12345678", paper=False)
    config = AppConfig(
        mode="live",
        broker="kis",
        symbols=["QQQ"],
        allow_live_trading=True,
        live_environment_authorized=True,
        kis=credentials,
    )
    paths = CanaryPaths(tmp_path / "canary", "2026-07-17")
    fingerprint = account_fingerprint(
        credentials.account_no,
        credentials.account_product_code,
    )
    state = CanaryState(
        "2026-07-17", "nonce", fingerprint, executable_sha256(executable),
        StateMode.ARMED, None, 0, 0, 0, 0, None,
    )
    CanaryStateStore(paths.state).save(state)
    paths.arm.parent.mkdir(parents=True, exist_ok=True)
    paths.arm.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "market_date": "2026-07-17",
                "account_fingerprint": fingerprint,
                "product": "kis-real",
                "base_url": "https://openapi.koreainvestment.com:9443",
                "executable_sha256": executable_sha256(executable),
                "policy_digest": CANARY_POLICY.digest,
                "windows_sid_sha256": "b" * 64,
                "state_nonce": "nonce",
                "issued_at": "2026-07-17T11:00:00+00:00",
                "expires_at": "2026-07-17T23:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return paths, config, executable


def run_canary(
    config: AppConfig,
    paths: CanaryPaths,
    executable: Path,
    broker: FakeKIS,
    session: MarketSession = SESSION,
):
    from nasdaq_auto_trader.live_canary_runner import (
        LiveCanaryRunRequest,
        run_live_canary,
    )

    return run_live_canary(
        LiveCanaryRunRequest(
            config, 1, broker, paths, executable,
            lambda: "b" * 64, lambda: NOW, lambda _: None, lambda _: session,
        )
    )
