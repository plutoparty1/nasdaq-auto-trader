# 자동 운영·안전 학습 구현 보고서

## 1. 기존 시스템 분석 요약

진입점은 `python -m nasdaq_auto_trader`와 Windows GUI다. 기존 기술 전략, Alpaca·한국투자증권 연동, 자동 종목 선택, 주문 전 리스크 검사, 전략 레지스트리, 감사 로그, GUI 설정과 세션 복구를 유지하고 운영 조정 계층만 추가했다.

## 2. 구현한 기능

- 공식 NASDAQ 캘린더 기반 정규장·주말·휴장일·조기 폐장·서머타임 판정
- 여덟 가지 운영 상태와 원자적 상태 저장
- 장중 거래, 장후 정산, 장외 학습 자동 분기
- 실제 완료 봉만 받는 학습 전용 파이프라인
- 학습 중복 잠금, 취소, 진행률, 동일 데이터 재학습 차단
- 검증 후보와 모델 해시가 포함된 학습 보고서 원자적 저장
- 구조화된 AI Trading Supervisor 판단 스키마
- 실거래 설정값과 환경변수의 이중 잠금
- 정량 시장 국면 분류와 데이터 부족 시 거래 금지

## 3. 주요 아키텍처와 상태 전환 방식

`AutomationCoordinator`가 UTC 시각을 공식 거래소 일정으로 판정한다. 개장 전에는 `PRE_MARKET_CHECK`, 장중에는 점검 통과 후 `LIVE_TRADING`, 장 마감 뒤에는 실제 계좌·포지션 새로고침을 수행하는 `POST_MARKET_RECONCILIATION`, 새 완료 데이터가 있으면 `OFF_HOURS_LEARNING`으로 이동한다. 모델 또는 리스크 설정 이상과 장 마감 계좌 대사 실패는 `SAFE_HALT`, 긴급 중지는 `EMERGENCY_STOP`으로 전환한다. 데이터·브로커의 모든 운영 상태를 독립적으로 사전 진단하는 완전한 헬스체크는 아직 남은 과제다.

## 4. 수정하거나 추가한 파일 목록

핵심 추가 파일은 `operating_state.py`, `automation_coordinator.py`, `controller_operations.py`, `learning_data.py`, `learning_report.py`, `learning_strategy_template.py`, `ai_trading_supervisor.py`, `market_regime.py`다. 기존 캘린더, 학습 러너, 컨트롤러, GUI, 설정 로더와 빌드 파일을 연결 수정했다.

## 5. 데이터베이스 변경사항

외부 데이터베이스 마이그레이션은 없다. `%LOCALAPPDATA%\NasdaqAutoTrader\runtime\operating_state.json`에 상태를 원자적으로 저장하고 학습 보고서는 `ai_quant_lab\strategy_specs\reports`에 저장한다.

## 6. 새 환경변수와 설정값

`NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES`가 새 실거래 환경 잠금이다. 정확히 `YES`여야 하며 JSON의 `allow_live_trading=true`, 계정 검증, 운영 모델과 사전 점검도 모두 통과해야 한다. 기본 예시는 `NO`다.

## 7. 실행 방법

```powershell
python -m pip install -r requirements-runtime.txt
python -m nasdaq_auto_trader --config config.kis.json gui
```

실행 파일은 `dist\NasdaqAutoTrader\NasdaqAutoTrader.exe`다.

## 8. 테스트 명령어와 테스트 결과

```powershell
python -m unittest discover -s tests
python -m compileall -q nasdaq_auto_trader tests
```

구현 시점 기준 테스트 373개가 통과했다. 실제 브로커 주문 전송은 금지했고 테스트 더블만 사용했다. 실제 CLI 프로세스, 빌드된 EXE 진단 모드, Tkinter 학습 버튼도 별도로 실행했다.

## 9. PAPER 모드 확인 방법

실거래를 끄고 연습 모드 또는 브로커 PAPER 계정을 사용한다. `학습만 실행` 결과의 제출 주문 수는 항상 0이어야 한다.

## 10. LIVE 활성화 절차

현재 배포의 운영 준비 판정은 드라이런과 PAPER까지다. 데스크톱 LIVE 경로는 설정으로 활성화할 수 있지만 실제 브로커 주문 E2E는 운영자가 소액으로 확인해야 하며, AI 퀀트 `live-cycle`은 계속 `shared_order_gateway_required`로 중단된다. 아래 값은 데스크톱 또는 제한된 명령줄 LIVE 경로에 필요한 조건이며 수익성이나 무인 운영을 승인한다는 의미가 아니다.

1. PAPER 검증과 운영 모델 수동 승인을 완료한다.
2. 브로커 계정과 리스크 한도를 검증한다.
3. JSON에서 `allow_live_trading=true`를 설정한다.
4. 비공개 `.env`에서 `NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES`를 설정한다.
5. 최종 주문 확인과 자동선택 승인 봉투를 생성한다.

GUI는 기존 정책대로 실거래 직접 활성화를 허용하지 않는다.

## 11. 장애 및 긴급 중지 테스트 방법

반드시 임시 테스트 경로와 테스트 더블을 사용해 손상 모델, 오래된 시세, 브로커 실패, 포지션 불일치를 주입하고 `SAFE_HALT`와 주문 0건을 확인한다. 실제 운영 파일이나 계좌로 장애 시험을 하지 않는다.

## 12. 현재 남아 있는 기술적 위험

- 수정주가·상장폐지·종목 변경 범위는 데이터 공급자 품질에 의존한다.
- 내장 후보는 결정론적 추세 추종 전략이며 신경망이나 로컬 LLM을 학습하지 않는다.
- 상관관계 변화 분석은 충분한 동기화 데이터가 없어 기본 비활성이다.
- 실거래 전 장기간 PAPER·그림자 검증이 필요하다.
- 수익이나 손실 방지를 보장하지 않는다.

## 13. 운영 전 확인해야 할 체크리스트

- 시스템 시각 자동 동기화
- API 키의 `.env` 전용 보관
- PAPER 주문·부분 체결·거절·재시작 복구 확인
- Champion 데이터 범위와 모델 해시 확인
- 손실·낙폭·주문 횟수·종목 비중 한도 확인
- 휴장일·조기 폐장 일정 확인
- 미체결 주문과 실제 포지션 일치 확인
- 긴급 중지 절차 연습

## 14. 롤백 방법

실행을 중지하고 `NASDAQ_AUTO_TRADER_ALLOW_LIVE=NO`로 되돌린다. 이전 실행 파일 또는 Git 커밋으로 복귀하되 `%LOCALAPPDATA%\NasdaqAutoTrader`의 상태와 감사 로그는 조사용으로 보존한다. 신규 후보만 격리하고 기존 Champion을 덮어쓰지 않는다.
