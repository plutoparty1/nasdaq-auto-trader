from __future__ import annotations


SETTINGS_SECTIONS_ADVANCED = [
    (
        "5. 위험 제한",
        [
            (
                "max_daily_buy_count",
                "하루 최대 매수 횟수",
                "int",
                "하루에 새로 사는 주문을 몇 번까지 허용할지 정합니다.",
            ),
            (
                "max_daily_sell_count",
                "하루 최대 매도 횟수",
                "int",
                "하루에 파는 주문을 몇 번까지 허용할지 정합니다.",
            ),
            (
                "max_daily_loss_rate",
                "하루 최대 손실률 (%)",
                "float",
                "예: 5 입력 = 하루 손실이 약 5%에 도달하면 새 매수를 막습니다.",
            ),
            (
                "cooldown_enabled",
                "주문 후 쉬는 시간 사용",
                "bool",
                "켜면 한 번 주문한 뒤 일정 시간 동안 새 매수를 쉬게 합니다.",
            ),
            (
                "cooldown_minutes",
                "주문 후 쉬는 시간(분)",
                "int",
                "예: 10 입력 = 주문 후 10분 동안 새 매수를 막습니다.",
            ),
            (
                "market_open_wait_minutes",
                "장 시작 직후 쉬기(분)",
                "int",
                "예: 10 입력 = 미국장이 열린 뒤 10분 동안 새 매수를 막습니다.",
            ),
            (
                "market_close_stop_minutes",
                "장 마감 전 매수 중지(분)",
                "int",
                "예: 10 입력 = 장 마감 10분 전부터 새 매수를 막습니다.",
            ),
        ],
    ),
    (
        "6. AI Trading Supervisor(선택 기능)",
        [
            (
                "ai_ticker_selection_enabled",
                "AI가 종목 고르기",
                "bool",
                "TradingAgents를 별도로 구성했을 때만 사용합니다. 과거 데이터 기반 종목 자동 선택과는 다른 기능입니다.",
            ),
            (
                "ai_order_qty_enabled",
                "AI가 수량 정하기",
                "bool",
                "별도로 구성한 TradingAgents가 주문 수량을 추천합니다. 최대 수량과 보유 한도는 다시 검사합니다.",
            ),
            (
                "ai_trade_decision_enabled",
                "AI Trading Supervisor 사용",
                "bool",
                "오랜 실전 경험에서 쓰는 자본 보존 원칙을 바탕으로 시장, 모델, 계좌와 리스크를 함께 살펴 거래 허용 또는 보류를 추천합니다. 경력이나 수익을 보장하지 않으며 직접 주문은 항상 차단됩니다.",
            ),
            (
                "ai_recommend_only",
                "추천만 보고 주문하지 않기",
                "bool",
                "켜면 AI 추천은 로그에만 보이고 어떤 주문도 만들지 않습니다. 처음에는 켜두세요.",
            ),
            (
                "require_confirm_after_ai",
                "AI 추천 후 한 번 더 확인",
                "bool",
                "켜면 AI 추천을 주문 후보로 쓰기 전에 사람이 다시 봅니다. AI 직접 주문은 항상 차단됩니다.",
            ),
            (
                "ai_min_confidence",
                "AI 최소 신뢰도",
                "float",
                "예: 0.7 입력 = AI 신뢰도가 70%보다 낮으면 주문하지 않습니다.",
            ),
            (
                "ai_max_order_qty",
                "AI 최대 주문 수량",
                "int",
                "AI가 추천해도 이 수량보다 많이 주문할 수 없습니다.",
            ),
            (
                "ai_candidate_tickers",
                "AI 후보 종목",
                "str",
                "예: AAPL, MSFT, NVDA, TSLA, QQQ. AI 선택은 이 목록 안으로 제한됩니다.",
            ),
            (
                "ai_decision_interval_minutes",
                "AI 판단 간격(분)",
                "int",
                "예: 5 입력 = AI 판단을 최소 5분 간격으로 사용합니다.",
            ),
            (
                "ai_retry_count",
                "AI 실패 시 다시 시도 횟수",
                "int",
                "AI 응답이 이상하거나 호출이 실패했을 때 몇 번 더 시도할지 정합니다.",
            ),
            (
                "ai_fail_action",
                "AI 실패 시 처리",
                "str",
                "skip_trade 또는 fallback_to_rule. 처음에는 skip_trade가 안전합니다.",
            ),
        ],
    ),
    (
        "7. 알림과 기록",
        [
            (
                "telegram_enabled",
                "텔레그램 알림 사용",
                "bool",
                "나중에 텔레그램 연결 정보를 넣으면 알림을 보낼 때 사용할 설정입니다.",
            ),
            (
                "discord_enabled",
                "디스코드 알림 사용",
                "bool",
                "나중에 디스코드 연결 정보를 넣으면 알림을 보낼 때 사용할 설정입니다.",
            ),
            (
                "notify_order",
                "주문이 생기면 알림",
                "bool",
                "매수/매도 주문이 만들어졌을 때 알려줍니다.",
            ),
            (
                "notify_signal",
                "조건이 맞으면 알림",
                "bool",
                "매수/매도 조건이 감지됐을 때 알려줍니다.",
            ),
            (
                "notify_error",
                "오류가 나면 알림",
                "bool",
                "API 오류나 설정 오류가 생겼을 때 알려줍니다.",
            ),
            (
                "save_log",
                "로그 파일 저장",
                "bool",
                "켜면 화면에 보이는 실행 기록을 파일에도 저장합니다.",
            ),
            (
                "log_path",
                "로그 파일 위치",
                "str",
                "예: logs/trader.log",
            ),
            (
                "stop_on_order_error",
                "주문 오류가 나면 자동매매 멈춤",
                "bool",
                "켜면 주문/API 오류가 생겼을 때 자동매매를 일시정지합니다.",
            ),
        ],
    ),
    (
        "8. 무인 자동운영",
        [
            (
                "unattended_operation_enabled",
                "컴퓨터가 켜지면 자동운영 시작",
                "bool",
                "실행 직후 장 상태를 확인해 자동운영을 시작합니다.",
            ),
            (
                "unattended_live_trading_enabled",
                "무인 실거래 별도 동의",
                "bool",
                "LIVE·환경 승인이 있어야 무인 주문합니다. 전략 승격은 수동입니다.",
            ),
            (
                "unattended_interval_minutes",
                "자동 점검 간격(분)",
                "int",
                "시장·학습·거래 조건 재확인 간격입니다. 기본 15분입니다.",
            ),
            (
                "daily_report_enabled",
                "매일 오전 전일 보고서 만들기",
                "bool",
                "최근 미국 거래일의 학습·주문·차단 결과를 저장합니다.",
            ),
            (
                "daily_report_hour",
                "보고서 생성 시각(시)",
                "int",
                "현지시간 0~23시입니다. 기본 오전 8시입니다.",
            ),
            (
                "daily_report_minute",
                "보고서 생성 시각(분)",
                "int",
                "현지시간 0~59분입니다.",
            ),
            (
                "daily_report_retention_days",
                "보고서 보관 기간(일)",
                "int",
                "보고서 자동 정리 기준입니다. 기본 90일입니다.",
            ),
        ],
    ),
]
