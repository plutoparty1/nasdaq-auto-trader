from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .ai_decision_manager import AIRecommendationProvider
from .ai_quant_lab.artifact_paths import (
    StrategyArtifactPaths,
    default_strategy_artifact_paths,
)
from .ai_quant_lab.audit_logger import AuditLogger
from .automatic_order_guard import AutomaticOrderGuard
from .automatic_risk import AutomaticRiskLimits
from .automatic_preflight import automatic_universe_block
from .broker import AlpacaClient, DryRunBroker, KISClient
from .config import AppConfig, validate_trading_mode
from .config_manager import TradingSessionState, TradingSettings
from .dry_run_market_data import DryRunMarketData
from .engine_ai import EngineAIMixin
from .engine_clients import build_default_client, use_offline_dry_run_data
from .engine_cycle import EngineCycleMixin
from .engine_orders import EngineOrderMixin
from .engine_portfolio import EnginePortfolioMixin
from .engine_types import (
    BrokerLike,
    BrokerResponsePayload,
    DecisionPayload,
    EngineCycleItem,
    JsonObject,
    MarketDataLike,
)
from .engine_utils import decision_to_dict
from .models import AccountSnapshot, Position
from .live_authorization import LiveAuthorizationRequest, create_live_authorization
from .quant_data.symbol_selector import SelectionReport
from .quant_data.resources import application_data_root
from .risk import RiskManager
from .session_state_persistence import load_session_state
from .strategy import TechnicalStrategy
from .trading_session_store import TradingSessionStore
from .trading_agents import TradingAgentsAdvisor


class TradingEngine(
    EngineCycleMixin,
    EngineAIMixin,
    EngineOrderMixin,
    EnginePortfolioMixin,
):
    def __init__(
        self,
        config: AppConfig,
        broker: BrokerLike | None = None,
        market_data: MarketDataLike | None = None,
        account: AccountSnapshot | None = None,
        positions: dict[str, Position] | None = None,
        clock: Callable[[], datetime] | None = None,
        trading_settings: TradingSettings | None = None,
        trading_session_state: TradingSessionState | None = None,
        ai_provider: AIRecommendationProvider | None = None,
        live_order_confirmation: bool = False,
        strategy_artifact_paths: StrategyArtifactPaths | None = None,
        automatic_order_guard: AutomaticOrderGuard | None = None,
        live_authorization_duration_minutes: int = 60,
        live_authorization_max_cycles: int = 12,
        live_authorization_started_at: datetime | None = None,
    ) -> None:
        validate_trading_mode(config)
        self.config = config
        self.strategy = TechnicalStrategy(config.strategy)
        self.risk_manager = RiskManager(config.risk)
        self.trading_agents = TradingAgentsAdvisor(config.trading_agents)
        self._account = account
        self._positions = positions
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.trading_settings = trading_settings
        self.ai_provider = ai_provider
        self.live_order_confirmation = live_order_confirmation
        self.strategy_artifact_paths = (
            strategy_artifact_paths or default_strategy_artifact_paths()
        )
        self.last_selection_report: SelectionReport | None = None
        self.automatic_risk_limits: AutomaticRiskLimits | None = None
        session_store = (
            automatic_order_guard.session_store
            if automatic_order_guard is not None
            else TradingSessionStore(
                application_data_root() / "runtime" / "trading_session.json"
            )
        )
        self.automatic_order_guard = automatic_order_guard or AutomaticOrderGuard(
            self.strategy_artifact_paths,
            session_store,
            AuditLogger(self.strategy_artifact_paths.audit_log_path),
        )
        automatic_enabled = bool(
            trading_settings is not None
            and trading_settings.auto_symbol_selection_enabled
        )
        self.automatic_preflight_reason = (
            automatic_universe_block(config, self._clock())
            if automatic_enabled
            else ""
        )
        self._persist_automatic_session = (
            automatic_enabled and trading_session_state is None
        )
        if self._persist_automatic_session:
            session_store.recover_interrupted_claims()
            self.trading_session_state = load_session_state(session_store)
        else:
            self.trading_session_state = trading_session_state or TradingSessionState()
        if (
            automatic_enabled
            and not self.automatic_preflight_reason
            and config.mode == "live"
            and live_order_confirmation
        ):
            self.automatic_order_guard.set_live_authorization(
                create_live_authorization(
                    LiveAuthorizationRequest(
                        config=config,
                        paths=self.strategy_artifact_paths,
                        now=live_authorization_started_at or self._clock(),
                        duration_minutes=live_authorization_duration_minutes,
                        max_cycles=live_authorization_max_cycles,
                    )
                )
            )

        default_client: AlpacaClient | KISClient | DryRunMarketData | None = None
        if self.automatic_preflight_reason:
            default_client = DryRunMarketData()
        elif market_data is None:
            default_client = (
                DryRunMarketData()
                if use_offline_dry_run_data(config)
                else build_default_client(config)
            )
        elif broker is None and config.mode != "dry_run":
            default_client = build_default_client(config)

        self.broker = broker or (
            DryRunBroker()
            if config.mode == "dry_run" or self.automatic_preflight_reason
            else default_client
        )
        self.market_data = market_data or default_client


__all__ = [
    "BrokerLike",
    "BrokerResponsePayload",
    "DecisionPayload",
    "EngineCycleItem",
    "JsonObject",
    "MarketDataLike",
    "TradingEngine",
    "decision_to_dict",
]
