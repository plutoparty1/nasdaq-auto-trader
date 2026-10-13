"""Reuse the ordinary trading controller with approval-scoped production clients."""
from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit
from urllib.request import Request

from .ai_quant_lab.types import JsonObject
from .app_controller import AutoTradeController
from .automatic_order_guard import AutomaticOrderGuard
from .broker import DryRunBroker
from .brokers.common import BrokerRequestError
from .brokers.kis_client import KISClient
from .config import AppConfig
from .config_settings import TradingSessionState, TradingSettings
from .engine import TradingEngine
from .production_checks import make_client
from .production_authorization import ProductionOrderGate
from .production_runtime import ProductionRuntime


class ReadOnlyMarket(KISClient):
    def _open_json(self, request: Request, label: str) -> JsonObject:
        if request.get_method() != "GET" and urlsplit(request.full_url).path != "/oauth2/tokenP":
            raise BrokerRequestError("simulation_order_transport_forbidden")
        return super()._open_json(request, label)


class ProductionController(AutoTradeController):
    def run_operating_cycle(self, force: bool = False):
        # Production is the existing approved strategy loop, never automatic research.
        return self.run_auto_cycle(force=force)


class ProductionEngineFactory:
    def __init__(self, runtime: ProductionRuntime, gate: ProductionOrderGate | None = None) -> None:
        self.runtime = runtime
        self.gate = gate
        self.mode = "waiting"
        self.client: KISClient | None = None

    def __call__(
        self, config: AppConfig, *, trading_settings: TradingSettings | None = None,
        trading_session_state: TradingSessionState | None = None,
        automatic_order_guard: AutomaticOrderGuard | None = None,
        live_order_confirmation: bool = False,
    ) -> TradingEngine:
        del config, trading_settings
        runtime = self.runtime
        if self.mode == "live":
            if self.client is None:
                raise RuntimeError("production_client_not_started")
            return TradingEngine(runtime.config, broker=self.client, market_data=self.client,
                                 trading_settings=runtime.settings,
                                 trading_session_state=trading_session_state,
                                 automatic_order_guard=automatic_order_guard,
                                 strategy_artifact_paths=runtime.paths,
                                 production_order_gate=self.gate,
                                 live_order_confirmation=live_order_confirmation)
        configured = make_client(runtime, read_only=False)
        reader = ReadOnlyMarket(configured.credentials, runtime.token_cache)
        return TradingEngine(replace(runtime.config, mode="dry_run", allow_live_trading=False),
                             broker=DryRunBroker(), market_data=reader,
                             trading_settings=replace(runtime.settings, dry_run=True, live_trading=False),
                             trading_session_state=trading_session_state,
                             automatic_order_guard=automatic_order_guard,
                             strategy_artifact_paths=runtime.paths)
