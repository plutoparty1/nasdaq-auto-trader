# 무인 자동운영 구현 보고

## 결과

- GUI 시작 시 저장 설정에 따라 15분 간격 무인 운영을 자동 시작한다.
- 미국 거래소 휴장일·서머타임·정규장 상태에 따라 장전 보충 학습, 장중 판단, 장후 대사와 완료 일봉 학습을 분리한다.
- 조회 장애는 주문 없이 다음 주기에 재점검하고, 주문 제출 결과 불명과 비복구 안전 사유는 자동 재개하지 않는다.
- Windows 현재 사용자 최소 권한 작업이 로그인 시와 매일 5분 반복으로 정확한 설치 EXE를 감시한다.
- 매일 오전 8시 이후 최근 완료 미국 거래일의 Markdown 보고서를 한 번 생성한다.

## 안전 조건

- 2026-07-17 설치본 읽기 전용 E2E에서 `dry_run=true`, `live_trading=false`, `submitted_order=false`를 확인했다.
- 무인 실거래 별도 동의 여부와 무관하게 LIVE 모드·환경 승인·현금·손실·보유수량·신호 claim·챔피언 전략 승격 조건을 우회하지 않는다.
- 주문 POST는 자동 재시도하지 않으며 중단된 제출 claim은 `uncertain`으로 복구한다.
- 보고서는 허용된 이벤트와 필드만 집계하고 API 키·토큰·계좌번호·원시 브로커 응답을 복사하지 않는다.

## 배포 및 관측

- 실행 파일: `C:\Users\u\nasdaq-auto-trader\dist\NasdaqAutoTrader\NasdaqAutoTrader.exe`
- 예약 작업: `NasdaqAutoTrader-Unattended`
- 운영 설정: `%LOCALAPPDATA%\NasdaqAutoTrader\trading_config.json`
- 브로커 자격증명: `%LOCALAPPDATA%\NasdaqAutoTrader\.env`
- 운영 상태: `%LOCALAPPDATA%\NasdaqAutoTrader\runtime`
- 감사 로그: `%LOCALAPPDATA%\NasdaqAutoTrader\ai_quant_lab\audit.jsonl`
- 일일 보고서: `%LOCALAPPDATA%\NasdaqAutoTrader\reports\daily-YYYY-MM-DD.md`

## 검증

- 전체 단위·통합·Windows Tk E2E 테스트 463개 통과.
- 테스트의 모든 `AutoTradeController`는 임시 세션 저장소를 명시하며 사용자 AppData를 읽거나 복구하지 않는다.
- 드라이런 엔진은 실제 브로커 객체가 주입되어도 `submit_order`를 호출하지 않는다.
- 장중 주문 전 시세·계좌 장애는 안전 재시도하고 주문 결과 불명 장애는 자동 재개하지 않는 경계 테스트가 통과한다.
- 지연 실행된 학습도 실행일이 아니라 완료 미국 거래일의 전일 보고서에 집계된다.
- PyInstaller 폴더형 빌드와 개인 자료 패키지 감사 통과.
- 예약 작업은 InteractiveToken, Limited, IgnoreNew, PT5M, StartWhenAvailable 계약으로 등록됨.
- 작업 XML에 브로커 비밀 이름이나 값이 없고 배포 폴더에는 `.env`가 없으며 AppData 개인 키 파일만 사용함.
- 최종 EXE SHA-256은 `225FE20C7A5C2C0E0A3E47DB57DECD80712D7FB63285A1B510D3C0E88199B2F1`이며 빌드와 설치본이 일치한다.
- 정확한 설치 경로에서 한 개만 실행되며 Windows 응답 상태가 정상임.
- 배포 EXE의 KIS 읽기 전용 조회에서 주문 가능액이 매수 필요액보다 작을 때 차단되고 제출 주문이 0건임을 확인함.
- 배포 EXE의 중복 실행은 기존 창을 복원하고 4초 안에 종료되며, 잘못된 명시적 CLI 입력도 숨은 대화상자 없이 종료됨을 확인함.
- 작업 스케줄러 콜드 재시작과 연속 2회 실행에서 정확히 한 PID가 유지됨을 확인함.
- 실제 Windows Tk 위젯 E2E에서 자동매매, 학습, 전일 보고서, 네트워크 오류 표시를 순서대로 실행하고 실제 주문 0건을 확인함.
- 전일 보고서 생성과 GUI 한글·버튼·무인 설정 레이아웃 독립 시각 검토 2건이 통과함.

## 최종 런타임 감사

- 가설 1, 설치본이 마지막 소스보다 오래됐을 수 있음: 빌드본과 설치본 SHA-256이 모두 `225FE20C7A5C2C0E0A3E47DB57DECD80712D7FB63285A1B510D3C0E88199B2F1`으로 일치해 기각함.
- 가설 2, 드라이런 CLI가 주문 제출 경로에 진입할 수 있음: 설치본 `buying-power`와 `day-test --dry-run` 모두 `submitted_order=false`였고 런타임 설정도 `dry_run=true`, `live_trading=false`여서 기각함.
- 가설 3, 예약 작업과 중복 실행이 두 프로세스를 남길 수 있음: 예약 작업을 연속 시작해도 설치 경로 PID는 1개였고 중복 실행은 5초 안에 종료되며 기존 프로세스가 응답 상태를 유지해 기각함.

2026-07-17 추가 독립 리뷰에서 프로세스 재시작 시 실거래 승인 수명이 갱신되는 P0을 발견해 영구 승인 저장소로 수정했고 재검토 PASS를 받았다. 동일 범위를 463개 전체 테스트, 엄격 Python 감사 및 설치본 E2E로 다시 확인했다. 최종 코드 품질, 금융 안전, 설치본 QA 검토도 PASS이며 계정의 승인 전략 부재는 별도 LIVE 차단 사유로 유지했다.
