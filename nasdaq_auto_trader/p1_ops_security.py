"""Explicit mode credentials and consent; neither grants live strategy approval."""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from .brokers.kis_client import KISCredentials
from .entry_comparison import JsonValue

CONFIRMATION = '실전 위험과 미검증 상태를 확인했습니다'
LIVE_BLOCKERS = (
    'p1_live_strategy_approval_binding_unavailable',
    'live_session_authorization_required',
)


def dedicated_environment(path: Path, environ: Mapping[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding='utf-8-sig').splitlines():
            line = raw.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key.strip().startswith('KIS_PAPER_'):
                    values[key.strip()] = value.strip().strip(chr(34)).strip(chr(39))
    values.update({key: value for key, value in environ.items() if key.startswith('KIS_PAPER_')})
    return values


def paper_credentials(values: Mapping[str, str]) -> KISCredentials:
    keys = ('KIS_PAPER_APP_KEY', 'KIS_PAPER_APP_SECRET', 'KIS_PAPER_ACCOUNT_NO')
    if not all(values.get(key, '').strip() for key in keys):
        raise ValueError('dedicated_paper_credentials_required')
    return KISCredentials(app_key=values[keys[0]], app_secret=values[keys[1]],
                          account_no=values[keys[2]], paper=True,
                          account_product_code=values.get('KIS_PAPER_ACCOUNT_PRODUCT_CODE', '01'),
                          timeout=10)


def live_request(account: str, allocation_usd: float, loss_stop_pct: float,
                 confirm: str) -> dict[str, JsonValue]:
    normalized = account.replace('-', '').strip()
    if (re.fullmatch(r'[0-9]{8,10}', normalized) is None or confirm != CONFIRMATION
            or not math.isfinite(allocation_usd) or allocation_usd <= 0
            or not math.isfinite(loss_stop_pct) or not 0 < loss_stop_pct <= .2):
        raise ValueError('explicit_account_allocation_loss_stop_confirmation_required')
    return {'schema_version': 1, 'account_sha256': hashlib.sha256(normalized.encode()).hexdigest(),
            'account_masked': '****' + normalized[-4:], 'allocation_usd': allocation_usd,
            'loss_stop_pct': loss_stop_pct, 'confirmed_at': datetime.now(UTC).isoformat(),
            'confirmation': confirm, 'approved_for_orders': False,
            'remaining_gate': LIVE_BLOCKERS[0]}


def live_review(request: dict[str, JsonValue] | None, version: str) -> dict[str, JsonValue]:
    return {'account': (request or {}).get('account_masked', '미지정'),
            'version': version, 'execution': 'run_p1_trader.cmd / Python source',
            'universe': 'CMCSA, HIVE, KDP (기존 고정 종목군)',
            'conditions': '기존 C 진입; 완성 일봉; 손절 8%, 익절 16%, 추적 8%/4%, 일반 기술적 매도 유지',
            'caps': '거래 위험 2%; 종목/전체 50%; 주문 $35; 현금 여유 5%; 계획 위험 합계 6%',
            'allocation_usd': (request or {}).get('allocation_usd', '미승인'),
            'loss_stop_pct': (request or {}).get('loss_stop_pct', '미승인'),
            'existing_holdings': '자동 인수/처분 안 함; P1 확인 체결분만 관리',
            'fees': '실제 계좌 수수료 미확인; 기본 편도 0.25%, 최소 $0는 추정',
            'readiness': '운영 연결 검증과 수익성 검증은 별개. 60거래일 독립 평가 보존/미완료.',
            'approval': '이 요청 저장은 주문 승인이 아님. 기존 승인 전략/계좌/세션 결합을 P1로 대체하지 않음.',
            'required_action': '전용 KIS 모의 인증/서버 확인; 실제 비용 확인; P1에 유효한 기존 전략 승인 및 실전 세션 승인 필요',
            'blockers': ['P1 전략에 결합된 기존 실전 승인 자료 없음', '해당 계좌/거래일의 실전 세션 승인 없음'], 'confirmation_phrase': CONFIRMATION,
            'approved_for_orders': False}
