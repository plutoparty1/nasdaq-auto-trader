# CMCSA 왕복매매 복원과 별도 EXE 검증

## 네 가지 결과
1. 실제 매수는 점수0/HOLD를 최소매수 정책이 BUY로 바꾼 거래다. 매도는 점수9 기술적 하락 신호다. 잘못된 진입을 제거하고 유효한 매도는 유지했다.
2. 기존 EXE 추출 정책은 합성 입력에서 HOLD→강제 BUY→보유 시 SELL9. 수정 EXE는 동일 합성 입력에서 HOLD/매수0이며 새로운 위험 신호·손절은 SELL을 유지한다.
3. 열 파일: `C:\Users\u\nasdaq-auto-trader\deploy-safe\roundtrip-20261013\NasdaqAutoTrader\NasdaqAutoTraderSafe.exe`. 폴더 전체가 배포본이다. 기본 GUI는 일시정지, 실거래는 별도 승인 전까지 코드에서 잠긴다.
4. 실제 EXE 출력: build_id=roundtrip-repair-20261013-r1, strategy=builtin_ai_volatility_target, version=data-b230423351524f87-catalogue-v5, mode=dry_run, order_lock=true. 원문 runtime-check.stdout.log 및 frozen-fresh-2.log, 독립 qa-review.json.

## 실제 원장
미국 거래일2026-10-12, CMCSA(컴캐스트/NASD). KIS inquire-ccnl 읽기 전용2회; 인증 갱신·주문·취소0회. actual-trade.json에 반환 필드 보존.

|항목|매수|매도|
|---|---|---|
|주문번호|0030128158|0030133087|
|원장 주문 시각 KST|2026-10-12 22:40:12|2026-10-12 22:45:13|
|감사 로그 제출 KST|22:40:12.916110|22:45:13.156463|
|실제 체결 시각|응답에 없음|응답에 없음|
|주문 지정가|$20.61000000|$20.61000000|
|실제 평균 체결가|$20.61000000|$20.61000000|
|주문/체결/잔량|1/1/0|1/1/0|
|판단 가격|$20.6100|$20.6000|
|실제 판단 점수|매수0|매도9|
|이유|below_long_regime,daily_minimum_best_affordable|below_long_regime,sma_downtrend,ema_downtrend,macd_negative,momentum_negative,donchian_breakdown|
|신호 라벨|20261012@2026-10-12T13:40:00+00:00|20261012@2026-10-12T13:45:00+00:00|
|실제 수수료·세금|확인 불가|확인 불가|

20.61은 반환 소수8자리 체결가에서도 동일하다. 확인한 정밀도에서 반올림으로 가려진 가격차는 없다. 비용 전 실현손익$0; 실제 비용 후 실현손익은 미확인이다. 제출/로그 시각을 체결 시각으로 사용하지 않았다.

근거: `C:\Users\u\AppData\Local\NasdaqAutoTrader\logs\trader.log` 205645행 매수,205753–205754행 매도. `C:\Users\u\AppData\Local\NasdaqAutoTrader\ai_quant_lab\audit.jsonl` 27113–27120 부근 전략·신호·주문. 원시 시세 타임스탬프/전체OHLCV/ATR는 저장되지 않았다. 위5분 라벨은 평가 슬롯이며 봉 완성 시각이 아니다. 같은 일봉 라벨을 확인했지만 동일OHLCV 여부나 새로운 위험 정보의 유무는 확정하지 않는다. 이전 거래 원인을 이번 근거로 쓰지 않았다.

최종 매도 함수는 TechnicalStrategy.decide→_sell_score. 코드 경로 EngineAutomaticCycleMixin._execute_automatic_symbol_cycle→EngineCycleMixin._run_rule_decision_cycle(nasdaq_auto_trader/engine_cycle.py)→RiskManager.build_order→_submit_or_block_order. 이번 로그는 stop_loss/take_profit이 아닌 기술적 매도다.

## 당시 실행본·설정·위험 복원
현재 원본 `dist/NasdaqAutoTrader/NasdaqAutoTrader.exe` SHA256 b34486f790bc45d0f6e73189999f197760c77da482c20dd1a14b94d768617cea, 수정시각2026-09-23T13:58:26.737499Z,P1모듈없음. PID43856 동일경로 프로세스가 거래일 이전 생성되어 계속 응답 중이다. 이후 새 배포본 발견되지 않았다. 거래 시점 EXE해시/완전한 설정 스냅샷 자체가 없으므로 현재 파일·프로세스·당시로그로 복원한 증거 수준을 구분한다.

당시 전략 builtin_ai_volatility_target/data-b230423351524f87-catalogue-v5. 인접 config.kis.json + 설치 trading_config.json이 설정 출처다. 현재 GUI 최소매수true,주문/최대보유1주,손절3%,익절5%,실행5분,live=true. GUI해시는 이전 보존값과 동일. 기본 위험1%, 학습 전략 위험3%, 최소매수 경로는 위험5%로 바꾸는 코드가 원본EXE에 존재한다. config손절7%를 GUI3%가 덮는다.

가장 가까운 계좌 기록22:35:30KST의 cash/equity/buyingpower=$62.91. 매수 순간 계좌평가액은 별도 저장되지 않았다. 이 값 기준 위험예산 기본1%$.6291,학습3%$1.8873,최소매수5%$3.1455. 고정3% 1주 손절 구성요소$.6183,고정선$19.9917. 계획위험은 max(고정거리,3×ATR); 실제 보호선은 여러 보호조건 중 먼저 충족되는 조건이다. 당시ATR/실제비용이 없어 초기 유효 손절거리와 비용 포함 계획손실 전체를 확정할 수 없다.

필수 회귀 equity54.0728143546/price20.61/stop8%/risk2%:1주위험1.6488>예산1.081456287092이므로 주문null. 원본RiskManager도2%는 차단하지만 최소매수5%를 적용하면 허용하는 메커니즘을 추출코드로 확인했다. 실제 거래의 근접잔액62.91/GUI손절3%는 사용자 필수 예제와 다르다.

새 배포본은 기존 GUI 기술지표를 적용하되 최소매수/강제주문/live/advisory override를 강제해제,기본위험1%/손절3% 유지. 모의 왕복비용0.5%는 명시적 보수 가정이며 실제수수료가 아니다. 예상 비용 후 손익을 기록하되 손실이라는 이유로 필요한 위험매도를 막지 않는다. 최종값·요청값·경로·SHA를 시작로그에 출력한다. 전략ID/버전/specdigest 불일치 시 중단,구버전 자동대체없음.

## 수정·실제 배포 검증
최소매수 신호·위험5% 우회 제거; flat진입의 동시 매수/매도 조건 차단. 자동 기술판단은 완성봉을 사용하며 기존 잠금/session store에 strategy/version/symbol/bar 공통 판단키를 영속화한다. 동일봉 반대판단·재진입·재시작 중복을 차단하고 저장불확실 시fail-closed. 손절/유효한 보호·시간청산 유지.

safe launcher는 독립appdata/registry/settings,비밀정보없는profile,irreversible order lock을 사용한다. GUI저장값으로live/minimum/TradingAgents override를 되살릴 수 없다. 자동시작/예약/liveCLI도차단.

새 EXE SHA256 61ccd1c47252d428211f264a97129bca8f0a7a8efbd2528f0e3e07de873cdd59. build-final.log의 PyInstaller완료,final-manifest.json참고. 원본EXE·설정은 deploy-backups/roundtrip-preserved-20261013에 보존.42개 원본EXE/설정/P1원장·프로토콜·소스해시 모두동일. 미커밋작업보존,커밋없음.

archive-reproduction.json은 원본EXE 순수정책과 합성100봉 대조다. 실제score0/9와 이유를 재현했지만 당시OHLCV전체재현은 아니다. 최종EXE frozen-fresh-1/2 별도프로세스 모두exit0,첫 합성정상gate BUY는 주문제출이 아닌gate계약시험,재시작HOLD+signal_key_submitted. 무신호3주기 주문0,동일봉보유반대HOLD,새완성봉기술위험SELL,새mark손절SELL+safe_release_order_lock,익절비용진단 유지,필수위험주문null,broker/cancel0. 독립QA14항목통과qa-review.json.

첫 frozen시험의 상태저장실패는 frozen-replay-1.stderr.log에 보존했다. 성공으로 세지 않았다. 실패모의fixture만 별도이름으로보존하고 동일EXE에서 정상저장/두프로세스재시작을 다시확인했다. OS실패원인은확정되지않음;당시C드라이브여유약148MB. 저장실패시신규판단은차단된다.

네트워크차단 관련152개 + 최종73개 회귀통과(일부겹침). portablebasedpyright 오류0/경고33,LSP설치없음. 새5모듈lint에unused timezone2건/차단예외TRY0041건남음;런타임오류와구분한다. 전체suite/장기백테스트미수행.

기본GUI도 새EXE PID37612로실행:응답true/window NASDAQ Auto Trader. 실제GUI로그20:35:02 드라이런/자동매매시작대기,20:35:04제출0/차단0. 스크린샷시각검증은하지않음. 시험용새GUI만CloseMainWindow로닫았고기존PID43856유지. gui-processes.json/gui.stdout.log참고.

## 운영 상태
별도수정배포완성,실거래는의도적으로잠김. 기존EXE는계속실행중이므로기존정책으로추가거래할위험은남는다. 임의종료/인수/보유·미체결처분하지않았다. 새EXE의주문제출은잠기며새GUI끼리중복은자체lock이막는다. 실거래전환은별도승인과기존프로세스·보유·미체결대사없이는허용하지않는다.
