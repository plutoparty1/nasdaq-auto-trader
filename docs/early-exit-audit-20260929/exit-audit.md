# 로컬 청산 경로 독립 감사

조사 기준: 2026-09-29, 현재 작업 폴더의 수정 전 소스. 이 문서는 실제 체결 로그 감사와 별개인 코드/격리 실행 증거다. 아래 재현은 실제 계좌의 최근 매도 원인을 입증하지 않는다. 제품 코드를 수정하지 않았으며 주된 수정 담당자가 작업한 이후 줄 번호는 이동할 수 있다.

## 실행 안전과 범위

- 브로커/트레이더/GUI/예약 작업을 실행하지 않았다. 네트워크 소켓 연결을 예외로 막은 프로세스 안에서 순수 전략 함수와 주입한 가짜 브로커/시세로 `TradingEngine.run_once()`를 구동했다.
- 엔진 재현은 임시 `LOCALAPPDATA`, 임시 전략 경로와 세션 저장소를 사용했다. 임시 디렉터리는 종료 시 제거했다. 기존 환경 파일, 계좌번호, 키, 토큰을 출력하지 않았다.
- 코드를 읽은 파일: `strategy.py`, `strategy_config.py`, `risk.py`, `engine.py`, `engine_cycle.py`, `engine_automatic_cycle.py`, `engine_orders.py`, `engine_portfolio.py`, `engine_clients.py`, `config_settings.py`, `config_runtime.py`, `session_state_persistence.py`, `automatic_order_context.py`, `automatic_order_guard.py`, `session_safety_policy.py`, `daily_buy_objective.py`, `entry_pricing.py`, `sell_monitor_rules.py`, `sell_monitor_types.py`, 관련 테스트.
- 이 분담에서는 설정 원문/프로세스/체결 로그를 읽지 않았으므로 현재 배포본의 활성 브로커와 전략 값, 실제 체결 원인은 별도 감사 결과와 결합해야 한다.

## 실제 소스 호출 경로

`TradingEngine.__init__` (`nasdaq_auto_trader/engine.py:67`)은 `TechnicalStrategy(config.strategy)`와 `RiskManager(config.risk)`를 만든다. `EngineCycleMixin.run_once()` (`engine_cycle.py:20`)은 자동 종목 선정 설정이면 자동 경로로 보내고, 그렇지 않으면 계좌/보유/봉을 불러온 뒤 보호 매도를 먼저 평가한다. 보호 매도는 AI보다 앞선다 (`engine_cycle.py:43`).

일반 의사결정 함수는 `engine_cycle.py:78`의 `_run_rule_decision_cycle()`이다. 관찰된 잔고의 최고가를 붙이고 `protective_exit()` 또는 `decide()`를 호출한다. `RiskManager.build_order()` 뒤에도 설정 검사와 제출 승인을 거친다. 실거래 승인, 시장 시간, 자동 전략 승인, 주문 의도 예약, 미체결 중복 검사, 최종 재확인은 `engine_orders.py:62`, `:108`, `:121`, `:159` 및 `automatic_order_guard.py:92`에 존재한다.

전용 HIVE 매도 모니터는 다른 정책이다. `sell_monitor_rules.py:16`은 HIVE 1주/매도 전용만 허용한다. 기본 `HiveSellMonitorConfig` (`sell_monitor_types.py:43`)는 이익일 때만 매도, 손실 매도 확인, 손절/트레일링/장 마감 강제청산 꺼짐을 가진다. `take_profit_pct=1.5`는 이 경로에서 퍼센트 단위이고 일반 전략의 `0.015`와 단위가 다르다. 이 모니터를 일반 자동 전략의 수정 대상으로 삼으면 안 된다.

## 확인된 오류와 설계 문제

|항목|수정 전 로컬 사실|격리 실행 결과|판단과 최소 변경 제안|
|---|---|---|---|
|A 고정/ATR 동시 청산|`strategy.py:110` 고정 손절, `:133` ATR 손절을 각각 독립 검사. 고정 손절→고정 익절→트레일링→ATR 손절→ATR 익절 순서.|진입 10, 고정 5%, ATR 0.02×3, 현재 9.94에서 `atr_stop_loss`. 고정 손절 9.50에 닿지 않았다.|전략 설계 문제. 기존 모드는 명명해 보존하고 실험 프로필만 fixed/entry_atr를 명시적으로 선택. 실효 손절과 우선순위를 기록.|
|A 비정상 ATR|`strategy.py:134` 결과에 유한/양수 검사가 없다.|ATR 0에서 매수가 그대로여도 `atr_stop_loss`. 함수 경계에 음수 ATR을 주입하면 동일. NaN이면 ATR 비교만 모두 false.|0은 정상 평탄 OHLC에서도 발생하는 실제 결함. 비유효 ATR로 손절/익절을 만들지 않고 먼저 평가하는 유효 고정 보호는 유지. 음수 주입은 방어 경계 검증이며 정상 OHLC ATR이 음수가 됨을 뜻하지 않는다.|
|A 변하는 초기 손절|`atr(bars, period)`를 매번 재계산. `Position`에는 진입 ATR/초기 손절 필드가 없다.|별도 진입 ATR 상태가 없음을 소스에서 확인.|실험은 최초 실제 보유/체결에서 초기 ATR과 손절을 확정. 상태 저장, 재시작, 추가 체결 처리 필요. 기존 보유에 추정 초기 ATR을 몰래 소급 적용하지 않음.|
|B 충돌|`strategy.py:49` 두 점수를 계산하나 flat 매수 조건 `:52`에 매도 점수 거부가 없다.|자연 OHLC 70봉에서 매수10/매도4. 동일 데이터와 flat→held→flat 상태만 바꾸면 buy→sell→buy.|재현된 논리 경계. 실제 전체 주문 왕복은 승인·중복·자금·체결에 의해 달라진다. 실험에서 매수 점수 충돌 거부와 완성 봉 청산은 분리 비교.|
|C 트레일링|`strategy.py:123`의 `entry < latest_price` 때문에 활성화 후 원금 아래에서는 보호가 사라짐.|진입100/최고102/현재100.98은 trailing 매도, 현재99는 보호 결론 없음(ATR 부족 2봉).|명시적 기존 이익보호 정책일 수 있어 실거래 정책을 바꾸지 말고 실험에서 활성화 상태를 유지. 사용자가 손실 매도를 제한한 전용 모니터는 유지.|
|D 위험 거리 불일치|`strategy.py:294`는 fixed/ATR 거리 max. `risk.py:139`는 equity×위험비율/거리로 수량 한도를 계산.|위 A 사례에서 실제 ATR 거리 0.06인데 sizing은 0.50달러.|min 단순 변경은 허용 수량을 8.33배 늘릴 수 있음. 실험의 선택된 초기 손절+왕복 비용을 공동 계산. 현행 max는 보수적인 스트레스 거리로 따로 이름 붙일 수 있음.|
|F 종목 선정 장애|`engine_automatic_cycle.py:57`에서 보호 신호를 구해도 `:73`에서 선정 수행 후 `:99` 보호 매도로 진행.|가짜 엔진, 보유 보호 신호, 정상 보유 봉, 선정 함수 OSError → `PreOrderCycleError market_data_unavailable`, 가짜 주문0.|신규 종목 선정/시세 장애와 기존 보유 보호를 분리할 필요. 유효한 승인 맥락이 없는 상태에서 무조건 제출하는 우회는 금지.|
|F 매수 가능금액 장애|`engine_cycle.py:140`은 sell에도 `_account_for_order()` 호출. KIS는 `engine_portfolio.py:75`에서 psamount를 조회.|고정 손절 신호가 있는 KIS 설정 가짜 엔진에 매수 가능금액 OSError → 보호 제출 전에 중단, 가짜 주문0.|매수 전용 정보 조회를 buy에만 수행하는 최소 오류 수정 가능. 매도 계좌/보유/승인 검증은 계속 유지.|
|F 매도 횟수|`config_runtime.py:160`은 이유와 무관하게 매도 상한 검사. `session_safety_policy.py:51`도 동일.|sell_count=1/max=1이면 `max_daily_sell_count_reached`.|안전 정책 문제. 보호 예외는 명시적 별도 정책/승인사항이며 자동으로 우회 금지.|
|F 일일 손실|`config_runtime.py:149`, `session_safety_policy.py:38`은 신규 buy에만 적용.|daily_loss_breached=True에서 sell 설정 검사 결과 None.|일일 계좌 손실 한도가 일반 설정 단계에서 보호 매도를 막는다는 가설은 반박됨. 개별 손절과 별개.|

### B의 자연 신호 재현 데이터

가격은 `100, 101, ..., 168, 180`이며 각 봉은 open=close−0.5, high=close+1, low=close−1, volume=1,000,000+index이다. `tests/test_indicators_strategy.py:29`의 `strategy_config_fixture(stop_loss_pct=.5, take_profit_pct=.5)`를 사용했다. 실제 계산 결과:

```text
buy_score=10: long_regime_up, sma_trend, ema_trend, macd_positive,
              momentum_positive, donchian_breakout, volume_confirmation
sell_score=4: rsi_overbought, bollinger_overextension, stochastic_overbought
actions=['buy', 'sell', 'buy']
```

점수 함수 mocking은 하지 않았다. 시장 방향이 강하면서 과열도 강할 수 있는 독립 합산 방식의 충돌이다. `automatic_order_context.py:36`은 YYYYMMDD 봉 시각에 운용 주기 시작 시각을 덧붙여 매 주기 다른 신호키를 만든다. 실제 중복 방지 기능은 존재하지만 이 방식은 동일 일봉의 새로운 주기 재진입을 항상 차단하는 장치가 아니다. 체결/주문 로그 없이 실제 반복 횟수를 확정할 수 없다.

### C의 상태와 비용

- 가격 손익: 100→100.98은 +0.98%, 1주면 +$0.98. 순손익은 여기서 양쪽 수수료, 스프레드, 슬리피지를 빼야 한다. 실제 계좌 수수료 원장이 이 감사에 없으므로 순이익을 확정하지 않는다.
- `config_settings.py:166`은 계좌 잔고의 market_value/qty만으로 최고가를 관찰한다. 과거 봉의 매수 전 최고가를 섞지 않는다. 30초/수분 관찰 사이의 실제 고가는 놓칠 수 있다.
- `session_state_persistence.py:10`과 `:27`은 최고가/종료표식/상태버전을 읽고 저장한다. `position_first_seen_at`은 저장하지 않으므로 보유시간 청산 타이머는 재시작 시 실제 체결시각과 달라질 수 있다.
- 격리 실행: 2주, 평균100, 최고104를 관찰한 후 1주/평균100/현재102는 최고104를 유지했다. 2주/평균101/현재102로 바뀌면 최고102로 초기화했다.
- `config_settings.py:187`은 평균단가 변경 시 초기화한다. 동일 평균단가의 추가 체결과 완전 청산 후 동일 가격 재진입(중간 flat을 관찰 못한 경우)은 수량/체결 ID 없는 상태로 구분할 수 없다. 이를 '부분 체결 전부 안전'으로 보고하면 안 된다.

### 설정/주문 경로의 추가 설계 유의사항

- `StrategyConfig` 소스 기본은 stop=0.07/take=0.18 (`strategy_config.py:32`), GUI 저장값 매핑은 별도로 덮어쓴다. 기본값을 실제 최종 적용값으로 단정하면 안 된다.
- 일반 보호는 `strategy.py:106`의 최신 봉 종가 대신 유효해 보이는 position.market_value/qty를 우선 사용한다. `Position`에는 시세의 원천 시각/통화/신선도가 없으므로 오래된 계좌 마크 여부를 이 함수만으로 알 수 없다. 일반 기술 신호는 봉 종가에 따른다.
- `engine_portfolio.py:26`은 `config.timeframe`을 시세 공급자에 전달한다. 운용 조회 주기를 ATR 봉 주기로 해석하면 안 된다.
- `daily_buy_objective.py:96`은 일일 1주 목표가 due이면 충분한 데이터가 있는 flat HOLD를 BUY로 바꾼다. `engine_cycle.py:148`은 이 주문에 5% 위험비율을 적용한다. 새 진입 veto를 추가할 때 이 경로에서 다시 매수가 되지 않는지 따로 확인해야 한다. 기존 요구 자체를 삭제하지 말고 실험 정책으로 분리한다.
- `entry_pricing.py:16`은 ask로 진입 가격을 바꿀 때도 위험 거리를 `max(기존 위험, ask×고정손절)`로 보정한다. 초기 ATR 실험을 일반 엔진에 연결한다면 sizing 함수만 바꾸어서는 일관성이 확보되지 않는다.
- `risk.py:162`의 매도는 설정 order_qty가 있으면 보유 전체가 아니라 그 수량까지만 청산한다. 보호 신호가 매 cycle 반복될 수 있으므로 부분 매도/보유수량 로그와 혼동하면 안 된다.
- 설정 cooldown은 신규 매수만 제한하지만 (`config_runtime.py:152`) 자동 세션 안전 예약 cooldown은 매수·매도 모두 제한한다 (`session_safety_policy.py:56`). 현행 설정이 켜져 있는지는 별도 확인 대상이다.

## 실행한 회귀 검증

Python 3.14.2에서 아래와 동등한 호출을 소켓 fail-closed wrapper 안에서 실제 실행했다. `PYTHONDONTWRITEBYTECODE=1`, `pytest -p no:cacheprovider`, autouse 임시 `LOCALAPPDATA`를 사용했다.

```text
python -m pytest -q -p no:cacheprovider
  tests/test_indicators_strategy.py
  tests/test_profit_protection.py
  tests/test_profit_protection_persistence.py
  tests/test_auto_symbol_profit_protection.py
  tests/test_fixed_quantity_risk_limits.py
  tests/test_order_retry_safety.py
  tests/test_preorder_cycle_failure.py
```

실제 wrapper의 핵심은 `with patch.object(socket.socket, 'connect', deny), patch.object(socket, 'create_connection', deny): pytest.main([...])`였다. 결과: **99 passed, 2 subtests passed in 8.06s**, 종료코드0. 이는 수정 전 기존 회귀 테스트 결과이며 새 오류 재현들이 통과하도록 고쳐졌다는 주장이 아니다.

독립적인 stdin 재현 세 번도 종료코드0이었다. 관찰 결과는 위 A/B/C/F 표에 모두 기록했다. 가짜 엔진 주문 제출 수는 전부0이었다.

## 권장 진단 이벤트

주문 제출 이벤트와 별도로 판단 시각에 보호 판단 이벤트를 기록하고, 체결은 체결 ID와 누적체결량으로 대사한다. 필요한 필드: symbol, observation time, position quantity/average basis, broker mark와 마지막 봉 가격/시각, 가격 출처, ATR/봉 주기, 고정/ATR/초기 손절과 활성화 여부, highest observed holding mark, trailing threshold, buy/sell scores, reason, policy/config digest, position lifecycle version, 주문/체결 연결 식별자의 비밀정보 없는 형태. 미확인 값은 null로 둔다.

현 시점 자료로는 어떤 실제 매도가 위 결함 때문에 발생했는지, 8%/10%로 넓히면 계좌 순이익이 개선되는지, 월10% 목표가 얼마나 자주 달성되는지를 이 분담에서 검증하지 않았다. 격리 코드 재현을 실제 운용 성과로 확대 해석하지 않는다.

## 후속 회귀 테스트 구현

소유 파일 `tests/test_early_exit_engine_safety.py`에 보호 매도와 KIS 매수 가능금액 장애의 실패 테스트 및 현행 정책 특성 테스트를 추가했다. 모든 엔진은 실제 `AppConfig(timeframe="1Day", mode="dry_run")`, 가짜 시세, 제출 시 무조건 실패하는 브로커, 임시 저장소를 사용한다. 안전 가드를 mocking하여 통과시키지 않는다.

실패 선행 명령:

```text
python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_early_exit_engine_safety.py
```

수정 전 결과: **1 failed, 7 passed in 2.90s**. 실패는 `test_protective_sell_survives_buying_power_outage`: `run_once` → `engine_cycle.py:140` → `engine_portfolio.py:75` → 가짜 `get_overseas_buying_power`의 OSError였다. 이는 타입/임포트 실패가 아니라 수정 대상 실행 경로의 재현이다.

통과한 특성 테스트는 자동 종목 선정 실패 시 fail-closed 중단, 보호 매도에도 적용되는 매도 상한, 일일 계좌 손실 한도의 신규 매수/기존 매도 구분, 최종 매도 잔고 재검사의 매수 API 비의존성, 미체결 주문 중복 차단, 재시작 후 제출 완료/불명확 상태의 동일 매도 신호 재전송 차단이다. 보호 매도 상한과 선정 실패 정책은 변경하지 않는다.

최종 재검사 함수의 현재 대응 파일은 `automatic_order_pending.py:39`의 `automatic_pending_order_block()`이다. 매도는 실제 보유 수량을 다시 확인한 뒤 `:60`에서 반환하므로 `:66`의 매수 가능금액 API를 호출하지 않는다. 이 부분은 이미 안전하며 추가 수정하지 않았다. 별도 AI 경로 `engine_ai.py:86`은 여전히 매수/매도 공통 조회이며 일반 보호 매도 우선 경로와 구분해 잔여 관찰사항으로 기록한다.

주 담당자가 `engine_cycle.py`를 buy일 때만 `_account_for_order()`를 조회하도록 수정한 뒤 독립 재검증했다. 기존 계좌/보유 로딩, 주문 승인과 중복 방지는 유지된다.

```text
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_early_exit_engine_safety.py tests/test_fixed_quantity_risk_limits.py tests/test_auto_symbol_risk_precision.py tests/config_engine_kis_cases.py
```

수정 후 결과: **85 passed, 2 subtests passed in 4.10s**, 종료코드0. 새 회귀 파일의 8개 사례와 기존 KIS 매수 가능금액/현금/정수 수량/위험 정밀도 테스트를 함께 통과했다. 브로커가 실제로 호출되면 즉시 실패하는 보호 매도 시나리오에서 `dry_run`, `submitted_order=False`, 원래 계좌 평가/현금, 1주 sell을 확인했다.
