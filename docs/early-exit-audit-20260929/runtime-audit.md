# 로컬 실행 경로·설정 감사 (2026-09-29)

이 문서는 변경 전 로컬 소스, 배포 디렉터리, 허용 목록으로 추린 JSON 설정, Windows 실행 프로세스·작업 스케줄러 메타데이터를 읽어 작성했다. 브로커 객체, GUI, 예약 작업을 실행하지 않았고 주문·취소·설정 저장·승인 갱신을 수행하지 않았다. API 키·토큰·계좌번호·환경파일 원문은 출력하거나 기록하지 않았다. 아래 줄 번호는 감사 시점 소스 기준이며 후속 수정으로 이동할 수 있다.

## 먼저 확인된 사실

- 사용자에게 알려진 개별 종목 **5% 손절과 달리, 설치 GUI가 참조하는 저장 설정은 개별 종목 고정 손절 3%**다. 5%는 고정 익절 및 별개의 GUI 일일 계좌 손실 제한에도 등장한다.
- GUI 설정에는 고정 손절 외에 기본 JSON의 ATR(일봉 14) × 3 손절이 남는다. 고정 손절과 ATR 손절 중 하나만 충족해도 매도 후보가 된다.
- 배포 실행 파일과 소스 직접 실행은 GUI 설정 위치가 다르다. 루트 `trading_config.json`은 dry_run이며, 기본 배포 GUI는 `%LOCALAPPDATA%/NasdaqAutoTrader/trading_config.json`을 읽는다. 후자는 `live_trading=true`, `dry_run=false`다.
- 브로커 설정은 KIS, 해외주식 USD, `kis.paper=false`다. GUI 매핑 후 모드는 live가 되고 `engine_clients.build_default_client()`가 KIS 실거래 자격증명 모드를 선택한다. **현재 계좌를 API로 조회한 것은 아니므로 실제 계좌 연결·잔고·상품 적합성까지 확인한 것은 아니다.**
- 감사 당시 실행 중인 해당 EXE 또는 프로젝트 명령행을 가진 Python/wscript 프로세스는 발견되지 않았다. 설치된 `NasdaqAutoTrader-Unattended`, `NasdaqAutoTrader-LiveCanary` 작업은 모두 **Disabled**다. 파일 설정은 실거래를 준비하지만 현재 실행 중이라고 표현할 근거는 없다.
- 최신 소스에서 일반 엔진의 청산은 `TechnicalStrategy`가 맡는다. 승격된 학습 전략은 종목 선정과 추가 위험 한도에 쓰이며, 그 전략의 청산 규칙으로 일반 엔진 청산이 대체되지 않는다.

## 작업 상태와 프로젝트 지침

작업 디렉터리는 `C:/Users/u/nasdaq-auto-trader`, 브랜치는 `main`이다. `git status --short`에 다수의 기존 수정·미추적 파일 및 과거 배포 EXE 삭제가 있었다. 전략·설정·자동주문·대사·백테스트·테스트 파일에도 기존 변경이 있으므로 모두 보존했다. 이 감사 작업의 작성 대상은 이 Markdown 한 파일뿐이다.

루트와 하위 디렉터리에 대해 `rg --files --hidden -g AGENTS.md`를 검색했고 AGENTS.md는 발견되지 않았다. 상위 `C:/Users/u/AGENTS.md`도 없었다. 세션에 주어진 프로젝트 규칙과 사용자 안전 조건을 적용했다. `.agents` 디렉터리는 있었지만 검색한 범위에서 지침 파일은 없었다.

## 실행 경로와 배포 상태

| 경로 | 확인 내용 |
|---|---|
| `nasdaq_auto_trader/__main__.py` | `python -m nasdaq_auto_trader` 진입점. `ai-quant`만 별도 operator CLI로 분기하고 나머지는 기존 CLI로 전달 |
| `nasdaq_auto_trader/cli_main.py:42` | `load_config(args.config)` 후 일부 명령의 CLI mode 덮어쓰기. GUI·once·loop·backtest·sell-monitor를 서로 구분 |
| `run_trader_gui.ps1` | 소스 루트로 이동 후 `python -m ... --config config.kis.json gui`. 별도 `--trading-config`가 없어 루트 JSON 사용 |
| `nasdaq_auto_trader/gui_launcher.py:31` | frozen이면 EXE 부모가 앱 디렉터리, 소스 launcher이면 저장소 루트 |
| `nasdaq_auto_trader/gui_launcher.py:37` | 기본 EXE 실행은 EXE 옆 `config.kis.json` + LocalAppData `trading_config.json`을 명시적으로 전달 |
| `nasdaq_auto_trader/gui_launcher.py:143` | 앱 디렉터리로 cwd 변경. 기본 argv 또는 사용자 제공 argv를 CLI에 전달 |
| `nasdaq_auto_trader/app_ui.py:29` | GUI 설정 로드, 자동선정·무인운영 강제 활성화, GUI confirm-before-buy/sell은 false로 매핑. 별도 live 주문 승인·계좌·세션 guard는 유지되는 구조 |
| `nasdaq_auto_trader/app_controller.py:59` | `apply_settings_to_app_config(base_config, trading_settings)`로 최종 앱 설정 합성 |
| `nasdaq_auto_trader/controller_operations.py:33` | 운영 상태기계, LIVE_TRADING 상태에서 `run_auto_cycle` |
| `nasdaq_auto_trader/engine_cycle.py:21` | auto selection 설정이 true이면 `_run_automatic_symbol_cycle`, 아니면 일반 고정 종목 cycle |
| `nasdaq_auto_trader/engine_automatic_cycle.py:28` | 계좌·보유 조회 → 보유 보호 판정 → 종목 선정 → 주문/보호 매도 경로 |
| `nasdaq_auto_trader/engine_cycle.py:104` | `strategy.protective_exit()` 또는 `strategy.decide()` → 시간 청산 → 일일 매수 목적 → 위험·설정·주문 guard |

배포물은 `dist/NasdaqAutoTrader/NasdaqAutoTrader.exe`이며 파일 크기 15,980,146 bytes, 수정 시각 2026-09-23 22:58:26.7374992 KST, SHA256은 `B34486F790BC45D0F6E73189999F197760C77DA482C20DD1A14B94D768617CEA`였다. `_internal`, `operations`, `config.kis.json`이 동반된다. 소스 변경이 이 EXE에 자동 반영되는 구조는 아니다.

예약 작업 두 개의 action은 `wscript.exe` → 배포 `operations/run_hidden.vbs` → 배포 `ensure_unattended_running.ps1` 또는 `ensure_live_canary_running.ps1` → 위 EXE를 가리킨다. 모두 Disabled, 마지막 실행 기록은 2026-09-09 21:10:10 KST, LastResult=0이었다. 예약 실행은 하지 않았다.

`runtime/operating_state.json`은 IDLE, 마지막 학습·대사 시장일 2026-09-25를 기록했다. 이 파일은 당시 기록이며 실시간 브로커 상태가 아니다.

**배포 한계:** EXE를 실행하거나 내장 Python 바이트코드를 추출 비교하지 않았다. 따라서 현재 소스와 EXE 내부 구현이 완전히 동일하다고 보증하지 않는다. 아래 유효값은 실제 배포 인접 JSON과 LocalAppData JSON을 현재 소스의 명시적 매핑에 적용한 결과다. EXE 내부 구현까지의 동일성은 별도 오프라인 패키지 검증 대상이다.

## 설정 저장 위치와 덮어쓰기

1. 기본 dataclass `AppConfig`, `StrategyConfig`, `RiskConfig` → `--config` JSON.
2. `config.load_config()`은 설정 파일 부모 `.env`를 읽고 현재 프로세스 환경변수로 덮어쓴다 (`config.py:199`, `_effective_env`). 환경변수는 자격증명·통화·거래소·live 환경 승인 등 허용된 항목에 적용되며 손절/점수를 일반적으로 덮어쓰는 기능은 없다.
3. 기본 EXE launcher는 `.env`를 먼저 프로세스에 setdefault한다. 우선순위는 기존 프로세스 환경 → LocalAppData `.env` → EXE 옆 `.env` → EXE 부모 `.env` (`gui_launcher.py:116`). 이후 `load_config`의 파일 환경보다 프로세스 환경이 우선한다. 로컬 감사 시 LocalAppData 파일의 KIS 자격증명 키 존재 및 live 환경 승인 여부만 boolean으로 확인했고 승인 값은 YES 상태였다. 현재 감사 셸 자체에는 live 환경 승인 변수가 없었다.
4. GUI는 `TradingSettings` 기본 → 선택된 trading JSON → `app_ui.launch_gui()` 자동운영 관련 덮어쓰기 → `apply_settings_to_app_config()`를 적용한다. `dry_run=true`면 `live_trading=true`보다 우선하여 dry_run이다. 현재 LocalAppData는 dry_run=false/live=true이므로 live로 매핑된다.
5. CLI `once/loop --auto-select`는 `automatic_runtime_config(..., preserve_mode=True)`를 통해 해당 CLI/AppConfig mode를 보존한다. 기본 일반 `once/loop`와 `backtest`는 trading JSON을 자동으로 합치지 않는다. 따라서 `show-config` 출력은 GUI 최종 유효 설정 전체를 뜻하지 않는다.
6. 자동선정 경로는 LocalAppData `ai_quant_lab/ai_quant_config.json` 및 승격 전략 spec에서 추가 위험 한도를 읽는다. 일부는 상한의 `min`이며, 일일 최소 매수 경로는 거래당 위험 비율을 별도로 5%로 덮어쓴다.

기본 배포 설정: `dist/NasdaqAutoTrader/config.kis.json`과 소스 루트 `config.kis.json`은 감사 대상 관련 값이 같았다. base mode=dry_run, allow_live=false, broker=kis, kis.paper=false, currency=USD, timeframe=1Day. base만 보면 고정 손절7%/익절18%지만 GUI에서 3%/5%로 교체된다.

루트 `trading_config.json`은 2026-09-01 수정, dry_run=true/auto_selection=false/손절3%/익절5%다. LocalAppData trading JSON은 2026-09-22 07:53:58 KST 수정, live=true/dry_run=false/auto_selection=true다. 두 파일을 혼동하면 운용 경로를 잘못 진단한다.

## 최종 유효 설정 표: 기본 배포 GUI 경로

아래 `B`는 배포 인접 `config.kis.json`, `G`는 LocalAppData `trading_config.json`, `Q`는 LocalAppData `ai_quant_lab/ai_quant_config.json`, `S`는 승격 전략 spec이다. `defaults → B → G`는 실제 합성 순서이며, Q/S는 별도 추가 제한이다.

| 항목 | 최종 값 | 단위 | 값의 출처 | 덮어쓰기 순서 | 사용하는 함수·위치 |
|---|---|---|---|---|---|
| 고정 손절 | 3.0 → 0.03, entry × 0.97 | G는 %, 전략은 비율 | G.stop_loss_rate | defaults7% → B7% → G3% | `config_runtime.py:38 apply_settings_to_app_config`; 감사 전 `strategy.py:98 _position_guard` |
| ATR 손절 | ATR(14 일봉) × 3 USD/주 | 가격 | B.atr_period=14, atr_stop_multiplier=3 | defaults → B, GUI는 이 값 유지 | `strategy.py:133 _position_guard`; `indicators.py atr` |
| 고정 익절 | 5.0 → 0.05, entry × 1.05 | %, 비율 | G.take_profit_rate | defaults18% → B18% → G5% | `config_runtime.py:39`; `strategy.py:112` |
| ATR 익절 | ATR(14 일봉) × 5 USD/주 | 가격 | B.atr_take_profit_multiplier=5 | defaults → B, G 매핑 없음 | `strategy.py:137` |
| 트레일링 활성화 | true, +2% | bool, 비율0.02 | G | strategy defaults → G | `config_runtime.py:43`; `strategy.py:115` |
| 트레일링 하락폭 | 최고가 대비 1% | 비율0.01 | G.trailing_stop_rate=1 | defaults → G | `strategy.py:123` |
| 매수·매도 기술 점수 | 매수 ≥5, 매도 ≥4 | 점수 | B | defaults → B, G 매핑 없음 | `strategy.py:49 decide` |
| RSI | 매수30, 매도70, 기간14 | 지수/일봉 | G 임계값, B 기간 | B → G 임계값만 | `config_runtime.py:36`; `_buy_score/_sell_score` |
| MA | SMA 5/20, EMA 5/20, long_sma20 | 일봉 수 | G short/long_ma_period | B SMA20/50, EMA12/26, long200 → G5/20/20 | `config_runtime.py:31` |
| 시간 청산 | 비활성, 저장된 최대180 | 분 | G | defaults → G | `engine_orders.py:215 _time_based_sell_decision` |
| 매수 주문 수량 | 1 | 정수 주 | G.order_qty | RiskConfig None → G1 | `risk.py:92 _buy_order` |
| 매도 수량 | min(보유수량, 1) | 주 | G.order_qty | 같은 매핑 | `risk.py:140 _sell_order` |
| 종목별 최대 보유수량 | 1; 추가매수 false | 주/bool | G | defaults → G | `risk.py:95`; `config_runtime.py:127 _buy_block_reason` |
| 종목당 최대 비중 | 50% | 계좌평가액 비율 | B0.50, min(Q0.50,S0.50) | B 제한 + Q/S 추가 제한 | `risk.py:77`; `automatic_risk.py:166 resolve_automatic_risk_limits` |
| 총 투자 노출 상한 | 50% | 계좌평가액 비율 | Q.max_total_exposure_pct | Q 추가 제한 | `automatic_risk.py:108 CycleReservationLedger.apply_limits` |
| 현금 여유분 | 계좌평가액 5% | 비율0.05 | B.min_cash_buffer_pct | defaults → B, G 매핑 없음 | `risk.py:79` |
| 최소 주문금액 | $50 저장, 고정 수량 분기에는 적용 안 됨 | USD | B.min_order_notional | B | `risk.py:92` 수량 분기가 `:117` 최소금액 검사보다 먼저 반환 |
| 최대 주문금액 | 일반 자동 매수 $35 (base $100도 적용) | USD | B100, Q35 | B 제한 + Q 제한 | `risk.py:85`; `automatic_risk.py:132` |
| 일반 거래당 위험 비율 | 1% (base1%, learned3% 중 더 엄격한 제한) | 계좌평가액 비율 | B.risk_per_trade_pct=.01, S=.03 | 각각 적용 | `risk.py:121`; `automatic_risk.py:123` |
| 일일 최소 매수 위험 비율 | 5% | 계좌평가액 비율 | `DAILY_MINIMUM_RISK_PCT=.05` | due일 때 base와 learned 양쪽 .05로 대체 | `daily_buy_objective.py:23`; `automatic_selection.py:120`; `engine_cycle.py:146` |
| 일일 계좌 손실 제한 | G5%; 자동선정 매수에는 Q2% 추가 제한 | 당일 시작 계좌평가액 대비 하락률 | G.max_daily_loss_rate=5, Q.max_daily_loss_pct=.02 | 각각 별도 gate | `config_runtime.py:172`; `automatic_risk.py:99` |
| 일일 매수 횟수 | 0 = 상한 없음 | 제출 시도 카운트 | G.max_daily_buy_count | defaults → G | `config_runtime.py:137`; `record_submitted_order` |
| 일일 매도 횟수 | 0 = 상한 없음 | 제출 시도 카운트 | G.max_daily_sell_count | defaults → G | `config_runtime.py:160` |
| 학습 주문 횟수 제한 | 0 = 상한 없음 | 건/일 | Q.max_orders_per_day=0 | Q 현재값, 과거 promotion snapshot1은 미사용 | `automatic_risk.py:73` |
| 재진입 시간 제한 | 비활성; 저장 minutes=15는 현재 미적용 | 분 | G.cooldown_enabled=false | defaults → G | `config_runtime.py:190`; `automatic_order_context.py:65` |
| 같은 일봉 중복 평가 | 5분 cycle별 signal timestamp로 구분 | 일봉 날짜 + cycle UTC | 설정 interval5분 | `automatic_order_context`에서 날짜만 있는 KIS 봉에 cycle stamp 부여 | `automatic_order_context.py:36` |
| 매수 장초 대기 | 0 | 분 | G | defaults → G | `config_runtime.py:210` |
| 장마감 신규 매수 중단 | 마감 전15 | 분 | G.market_close_stop_minutes | 기본10 → G15 | `config_runtime.py:202 _market_time_buy_block` |
| 일반 엔진 장마감 강제청산 | 별도 구현 확인 안 됨 | 해당 없음 | 위 15분 값은 신규 매수 제한 | 해당 없음 | 시간 매도와 HIVE monitor 별도 |
| 자동매매 평가 주기 | 5분=300초 | 분/초 | G.unattended_interval_minutes | CLI GUI default60분보다 start 시 G가 우선 | `app_ui_actions.py:16 _start_unattended_operation` |
| GUI 보유현황 갱신 | 기본15초 | 초 | CLI default; 실행 중 argv 확인 불가 | `--portfolio-refresh-seconds`가 있으면 대체 | `cli_parser.py:62`; `app_ui_actions.py` |
| 실제 기술지표 봉 주기 | 1Day | 일봉 | B.timeframe | 기본 → B; GUI 수정 없음 | `engine_portfolio.py:20`; `brokers/kis_market.py:105` |
| 조회 기간·개수 | lookback260일, limit1000 | 달력일/봉 수 | B | defaults → B | `_load_recent_bars`; KIS는 단일 dailyprice 응답만 처리 |

일일 손실 gate는 신규 매수 중단을 의미하며 계좌 손실5% 도달 시 모든 보유분을 자동 청산한다는 뜻이 아니다. G의 `%` 표현 5는 `/100`되어 0.05가 된다. S/Q/B의 `_pct` 값은 이미 비율이다. HIVE monitor의 `stop_loss_pct=-1.0`은 별도 모듈의 부호 있는 퍼센트 표현이며 일반 전략 `stop_loss_pct=0.03`과 직접 교환할 수 없다.

카운터는 실제 체결 수가 아니라 `record_submitted_order()`의 비차단 제출 시도에 의해 증가한다. 진짜 체결 분석에서 카운터를 매매 건수로 사용하면 안 된다.

## 학습·자동선정과 일반 청산의 차이

LocalAppData의 승격 전략은 `builtin_ai_volatility_target`, 버전 `data-b230423351524f87-catalogue-v5`, status=champion, mode=live, allowed_for_live/manual_approval=true로 기록되어 있다. `quant_data/symbol_selector.py:198 _resolve_live`가 이 파일을 읽어 spec을 선택한다. 해당 spec은 `position_sizing.risk_per_trade_pct=0.03`, `max_single_position_pct=0.5`다.

`ai_quant_lab/ai_quant_config.json`의 현재 live_trading=false/dry_run=true/controlled_live=false는 독립 AI quant 실행 경로 설정이다. 일반 GUI 엔진은 `resolve_automatic_risk_limits()`에서 이 파일의 위험 한도를 읽지만 이 세 mode 값을 GUI mode에 복사하지 않는다. 따라서 이 파일만 보고 일반 GUI 전체가 dry_run이라고 결론 내릴 수 없다.

학습 전략은 `select_symbols()`의 signal/rank 함수에 사용된다 (`symbol_selector.py:110`). 일반 엔진 생성자는 `TechnicalStrategy(config.strategy)`를 만든다 (`engine.py:80`). 선택 후 주문 후보는 이 TechnicalStrategy가 재판정한다 (`engine_cycle.py:104`). 학습 전략 평가 결과를 GUI 일반 청산 전략 전체의 성과로 해석하면 서로 다른 실행 규칙을 혼동한다.

일반 CLI `backtest`는 `backtest.py.Backtester`에 `TechnicalStrategy`와 `RiskManager`를 넘긴다 (`cli_commands_basic.py:28`). GUI 야간 학습은 별도 `ai_quant_lab/backtest_engine.py.BacktestEngine`을 사용한다 (`learning_runner.py:13`, `:157`); 학습 준비 코드에는 starting_equity 100,000.0 기준도 있다 (`:109`). 이 숫자는 8만 원의 소액 계좌 증거가 아니다.

Q의 수수료 모델은 commission_bps=1, slippage_bps=5다. 로컬 설정에 저장된 모델 가정일 뿐 실제 KIS 수수료·최소수수료를 증명하지 않는다.

## 일일 최소 매수·최소 종목·교체 요구

- `daily_minimum_buy_enabled=true`는 구현되어 있다. 당일 원주문 매수 체결을 대사하고 누적 체결 1주가 없을 때 due를 만든다. 불확실·미완결 체결 이력은 due를 false로 막는다 (`daily_buy_objective.py:32`).
- due이면 미보유 hold 신호를 buy로 바꾸는 `daily_minimum_decision()`이 있다 (`:96`). 순위에서도 최상위 1개를 선택한다 (`symbol_selector.py:116`). 따라서 본래 기술 매수 점수 기준을 충족하지 않은 종목도 위험·잔고 등 나머지 조건을 통과하면 매수할 수 있다. 매도 점수 충돌과 비용 분석은 이 추가 진입 경로를 포함해야 한다.
- 이 경로는 일반 1%/학습3% 거래당 위험 제한을 **양쪽 모두 5%로 바꾸는 별도 정책**이다. 사용자 가정의 손절5%와 의미가 다르다. 8만 원 가정으로 거래당 계획 손실 한도 4,000원에 해당하지만 현 코드 계산에는 실제 왕복 비용이 들어있지 않다.
- `daily_forced_order_enabled=true`도 저장되어 있으나 현재 `.py` 검색 결과 dataclass 선언 외 실행 코드 사용이 없었다. 이 값만으로 강제 교체매도가 활성이라고 단정할 수 없다.
- 최소 2종목 보유, 현금 확보를 위한 강제 종목교체 매도 구현은 현재 일반 엔진 경로에서 발견되지 않았다. 해당 요구를 임의로 없앤 것이 아니라 현 소스에 대응 구현을 찾지 못한 결과다. 일반 cycle은 보유 종목을 평가 목록에 합치지만 선정 탈락만을 이유로 청산하는 분기는 없다.

## HIVE 1주 전용 매도 모니터

`sell-monitor`는 일반 GUI cycle과 다른 CLI 명령이다 (`cli_main.py`, `cli_commands_special.py:101`). `HiveSellMonitorConfig`와 `SellMonitorRulesMixin`을 쓰며 HIVE, 정확히1주, sell-only, 추가매수 불가를 강제한다 (`sell_monitor_rules.py:15`).

기본값은 익절 +1.5%, 손절 비활성, 트레일링 비활성, 장마감 강제매도 비활성, 수익일 때만 매도, 손실 시 보유 및 손실매도 승인 요구다 (`sell_monitor_types.py:43`). stop_loss_pct=-1.0, trailing_stop_pct=0.8이 저장되지만 해당 기능이 비활성이면 발동하지 않는다. 가격/호가 polling은 기본30초이고 일봉 ATR이나 기술점수5/4를 사용하지 않는다.

일반 TechnicalStrategy의 3% 손절을 수정해도 이 모니터의 정책을 바꾼 것은 아니다. 반대로 이 모니터 수정만으로 일반 자동선정 엔진의 조기 매도를 해결했다고 해서는 안 된다. 모니터는 별도 기존 보호 정책으로 유지해야 한다. 감사 시 이 monitor를 실행 중인 프로세스는 확인되지 않았다.

## 조기 청산과 관련된 실행상 확인 사항

1. `_position_guard`는 고정 손절 → 고정 익절 → 트레일링 → ATR 손절 → ATR 익절 순서다. 여러 조건이 동시에 충족되어도 첫 이유만 반환된다. 단순 reason 하나로 다른 조건이 비충족이었다고 추론할 수 없다.
2. 보호 가격은 잔고의 `market_value / qty`가 양수이면 그것을 우선하고, 그렇지 않으면 최신 일봉 close를 사용한다 (`strategy.py:106`). 일반 기술점수는 bars의 close로 계산한다. 이 둘은 같은 시각의 같은 가격이라는 보장이 없다. Position에 가격 timestamp가 없어 원래 보호 판정 가격의 신선도를 사후 증명하기 어렵다.
3. KIS 데이터는 `timeframe != '1Day'`를 거절한다. 5분마다 조회한다고 ATR·RSI·MACD가 5분봉 지표가 되는 것이 아니다. 일봉 timestamp는 YYYYMMDD이고 일반 전략은 완성봉 여부로 기술 청산을 묶지 않는다.
4. 자동주문 문맥은 일봉 날짜에 5분 cycle stamp를 붙여 다른 cycle을 구분한다. 주문 중복 방지 기능은 있지만 이것만으로 같은 일봉의 매수→매도→재매수 왕복을 금지하는 것은 아니다.
5. 고점은 보유 관찰 시점의 `market_value/qty`로 갱신되고 session store에 저장한다. 같은 평균매수가이면 최고가를 유지한다 (`config_settings.py:165`, `session_state_persistence.py:9`). 매수 시각이 아니라 first-seen 타이머이며 first-seen 시각 자체는 감사 전 persistence에 저장되지 않는다. 시간 청산은 현재 비활성이라 현 증상 원인으로 확정하지 않는다.
6. 트레일링은 `entry < latest_price`가 추가 조건이다. 이미 활성화된 후 매수가 아래로 급락하면 트레일링 분기는 불충족으로 바뀐다. 그때 고정/ATR 손절은 별도 판정된다. 이는 조기매도보다 보호 공백 위험이며 기존 정책 변경과 구분해야 한다.
7. 신규 선정 오류가 보호 판정 후에도 영향을 줄 수 있다. 감사 전 `_execute_automatic_symbol_cycle()`은 보호 종목을 찾은 뒤에도 selection을 수행한다. selection의 특정 예외는 보호 주문 분기 전에 cycle을 실패시킬 수 있다 (`engine_automatic_cycle.py:72`). 모든 데이터 실패에서 보호를 실행할 수 있다는 뜻은 아니며 보유 자체의 유효 시세와 계좌 확인은 필요하다.
8. 일일 매도 상한이 양수이면 `_sell_block_reason()`은 보호/일반 구분 없이 차단한다. 현재 G=0이어서 그 상한은 발동하지 않지만 실험 변경 시 보호 정책 충돌을 검증해야 한다. 기존 승인·계좌·pending 주문 guard까지 우회해도 된다는 뜻은 아니다.
9. GUI의 15초 포트폴리오 갱신에서 익절 도달을 감지하면 operating cycle을 강제 재평가할 수 있다 (`app_ui_actions.py:163`). 따라서 모든 매도가 정확히 5분 간격으로만 발생한다고 추론하면 안 된다.

이 문서는 위 실행 가능성과 설정을 확인했으며 최근 실제 체결의 매도 원인 빈도·손익을 확정하지 않는다. 그 결론에는 체결 대사 자료와 당시 설정·가격·시각 로그가 필요하다.

## 재현 가능 감사 명령과 한계

실행한 종류: `git branch --show-current`, `git status --short`, `rg --files --hidden -g AGENTS.md`, 제한 범위 `rg -n`, `nl -ba`/`sed`로 소스 읽기, JSON에 허용된 전략·위험·mode 필드만 `ConvertFrom-Json` + `Select-Object`, `Get-CimInstance Win32_Process` 후 프로젝트 매칭 프로세스의 PID/경로/생성시각만 선택, `Get-ScheduledTask`/`Get-ScheduledTaskInfo`, `Get-Item`, `Get-FileHash -Algorithm SHA256`.

계정·자격증명 필드를 포함하는 JSON 전체 출력, `.env` 원문 출력, broker API/GUI/EXE 실행, scheduled task 실행·변경은 하지 않았다. 이 감사 하위 작업에서는 테스트·백테스트를 실행하지 않았으므로 테스트 통과를 주장하지 않는다. 소스 판단의 회귀 검증과 체결 분석은 별도 결과물과 연결해야 한다.
