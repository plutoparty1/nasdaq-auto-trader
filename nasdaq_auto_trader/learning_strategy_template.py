from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from nasdaq_auto_trader.ai_quant_lab.operator_market_data import BarsBySymbol
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject


def candidate_payload(bars_by_symbol: BarsBySymbol) -> JsonObject:
    data_version = _data_version(bars_by_symbol)
    return {
        "strategy_id": "builtin_trend_following",
        "version": data_version,
        "strategy_family": "trend_following",
        "description": "완료된 실제 일봉에서 검증하는 추세 추종 후보",
        "research_basis": {
            "provider": "insane_search",
            "research_ids": ["research-trend-following-brock-lakonishok-lebaron-1992"],
            "source_ids": ["doi:10.1111/j.1540-6261.1992.tb04681.x"],
            "summary": "이동평균과 거래범위 돌파 규칙의 부트스트랩 검증 연구를 후보 근거로 사용",
        },
        "universe": {"symbols": sorted(bars_by_symbol), "selection_method": "configured_universe", "filters": {}},
        "signals": [{"type": "trend_following", "lookback_days": 20, "weight": 1.0}],
        "entry_rule": {"type": "weighted_score", "threshold": 0.2, "top_n": 1},
        "exit_rule": {
            "stop_loss_mode": "atr_multiple",
            "stop_loss_atr_multiple": 2.0,
            "take_profit_mode": "atr_multiple",
            "take_profit_atr_multiple": 4.0,
            "trailing_stop": True,
            "max_holding_days": 60,
        },
        "position_sizing": {
            "method": "volatility_target",
            "risk_per_trade_pct": 0.001,
            "confidence_adjusted": True,
            "max_single_position_pct": 0.02,
        },
        "risk_controls": {
            "use_kill_switch": True,
            "block_if_data_stale": True,
            "block_if_spread_abnormal": True,
            "block_if_daily_loss_limit": True,
            "block_before_market_close": True,
        },
        "metadata": {
            "created_by": "deterministic_training_pipeline",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _data_version(bars_by_symbol: BarsBySymbol) -> str:
    digest = hashlib.sha256()
    for symbol in sorted(bars_by_symbol):
        digest.update(symbol.encode("ascii"))
        for bar in bars_by_symbol[symbol]:
            digest.update(f"{bar.timestamp}|{bar.open}|{bar.high}|{bar.low}|{bar.close}|{bar.volume}".encode("utf-8"))
    return f"data-{digest.hexdigest()[:16]}"
