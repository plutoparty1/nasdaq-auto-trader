# 실행 경로 리팩터링 및 GS Quant 분석

Date: 2026-09-08 | Status: 소스·빌드·무주문 검증 및 독립 리뷰 완료; 실거래 활성화 제외

## 판정의 범위

실행 가능한 프로그램의 품질 개선과 실계좌 운용 승인은 별개다. 이번 작업은 실제 주문을 보내거나 수익을 검증하지 않는다. 조회 전용 카나리 사전점검 결과는 `ready=false`, `existing_position`, `cash_below_canary_gate`였다. 이 결과를 일반 전략 LIVE 게이트의 판정으로 바꾸어 말하지 않는다.

## 저장소 조사

변경 전 Python 소스 224개를 목록화하고 실행·연구·설정·배포 계열을 분담 조사했다. 핵심 주문/연구 경로의 구현과 호출 관계, 관련 테스트를 검토했다. 전체 파일의 모든 줄이나 모든 가능한 시장 상황을 증명했다는 의미는 아니다.

| 계열 | 판정 | 근거와 처리 |
| --- | --- | --- |
| broker/brokers | 유지 | KIS·Alpaca·dry-run 구현. 주문 POST 자동 재시도 금지, 잔고·대사 경계 보존 |
| engine/automatic selection | 정리 | 정상 전략·보호매도 유지, 판단 무관 최소 매수와 전용 캐시 우회 제거 |
| risk/automatic risk/execution guards | 유지·수정 | 고정 주수의 공통 위험 상한 누락 수정, 연구실의 공유 주문 게이트 차단 유지 |
| live authorization/session/claims/locks | 유지 | 승인 수명·계좌 결합·중복 주문·원자적 예약·감사 기능은 삭제 대상 아님 |
| live canary/day trade/sell monitor | 유지 | 별도 명시적 실주문 표면. 일반 자동매매 전략 또는 수익 증거로 취급하지 않음 |
| learning/AI quant/registry/paper shadow | 이름·계산 정리 | 검증 파이프라인과 승인 보존. 실제 온라인 학습이라는 해석 제거 |
| features/indicators/strategies/market regime | 계산 정리 | 통계 중복과 beta 정렬 수정. 사용하지 않는 기본값을 수익 근거로 승격하지 않음 |
| AI decisions/TradingAgents | 수정 | 신뢰도 없는 언어모델 행동 문구를 실행 가능한 추천으로 포장하지 않음 |
| app/controller/settings/config | 유지 | 현재 GUI·저장 형식·운영 상태·시세 회복 동작 및 개인 설정 보존 |
| CLI/launcher/frozen diagnostics/package audit | 유지 | 운영 진입점과 안전한 배포 검증 표면 |
| unattended/report/scripts | 유지 | 로그인 기반 감시·복구·보고. Windows 로그인 전 자동 실행 보장 없음 |
| dist/build/deploy archives | 보존 | 제품 로직이 아니며 이전 버전 복구 자료일 수 있어 일괄 삭제하지 않음 |

얇은 `app.py`, `cli.py`, `settings_window.py` 등의 파사드는 현재 소비자가 있어 무조건 삭제하지 않는다. 제거한 코드와 기존 테스트의 요구사항 변경은 최종 diff로 복구할 수 있다. 사용자 문서·설정·계좌 상태는 삭제하지 않는다.

## GS Quant 조사 및 이식 경계

공식 저장소 고정 스냅샷: [`a1427df06d55abdf9368c9766a68f1cadc713d5f`](https://github.com/goldmansachs/gs-quant/tree/a1427df06d55abdf9368c9766a68f1cadc713d5f).

| 영역 | 적용 판단 |
| --- | --- |
| timeseries/econometrics, statistics | 수익률·표본 변동성·beta·낙폭의 로컬 계산 정의를 참고해 표준 라이브러리로 구현 |
| technicals | 기존 지표와의 정의 차이를 확인. 동일 이름이라는 이유로 전략 의미를 바꾸지 않음 |
| backtests/analytics/models/instrument/interfaces | 비용·평가 모델 참고. 기존 KIS 현금주식 엔진을 기관 파생상품 가격 엔진으로 교체하지 않음 |
| api/data/markets/risk/measures | 인증·데이터 권한 또는 원격 가격 서비스에 의존하므로 미이식 |
| entities/content/workflow/tracing/target/config | GS 업무·API 모델 계열이며 현재 브로커 실행 소비자가 없음 |
| documentation/test/mcp/skills | 계약·테스트·사용 문서 조사 대상으로만 사용 |

참고 계약: [econometrics](https://github.com/goldmansachs/gs-quant/blob/a1427df06d55abdf9368c9766a68f1cadc713d5f/gs_quant/timeseries/econometrics.py), [statistics](https://github.com/goldmansachs/gs-quant/blob/a1427df06d55abdf9368c9766a68f1cadc713d5f/gs_quant/timeseries/statistics.py), [공식 테스트](https://github.com/goldmansachs/gs-quant/tree/a1427df06d55abdf9368c9766a68f1cadc713d5f/gs_quant/test/timeseries).

전체 SDK 또는 Goldman 코드를 그대로 복사했다는 의미가 아니다. 입력·빈 데이터·단위·주기 계약을 이 프로그램에 맞추어 명시해야 한다. GS 일부 함수의 퍼센트 출력과 로컬 소수 비율을 혼동하지 않는다. 원격 무위험금리 곡선을 사용하는 Sharpe 경로를 직접 호출하지 않는다. 수학 참고에 따른 로컬 Sharpe의 무위험수익률 가정은 별도로 문서화한다.

Upstream은 [Apache-2.0](https://github.com/goldmansachs/gs-quant/blob/a1427df06d55abdf9368c9766a68f1cadc713d5f/LICENSE)이며 직접 소스를 재배포할 때 LICENSE/NOTICE를 보존해야 한다. 현재 전체 SDK 의존성을 추가하지 않는다. `requires-python >=3.10`은 3.14를 배제하지 않지만 3.14에서의 실행 검증을 대신하지도 않는다.

## 추가 참고 자료와 학습 기능

사용자가 제공한 [단축 링크](https://m.site.naver.com/2geBo)는 [퀀트 트레이딩 시 리스크와 성과 측정하는 방법](https://infomore.kr/퀀트-트레이딩-시-리스크와-성과-측정하는-방법/)으로 연결된다. 공개 본문을 읽고 수익률만으로 평가하지 않는다는 원칙을 적용했다. 이 글은 학습 알고리즘 구현이나 수익성 실증 자료는 아니다.

- 낙폭·변동성·위험조정수익: 실제 계산으로 정정하고 Calmar(CAGR/최대낙폭)를 추가한다.
- 비용: 기존 양방향 수수료·슬리피지를 유지하고 마지막 청산 비용을 같은 시점의 자산 평가에 반영한다. 세금·환전·시장충격을 모두 모델링했다고 주장하지 않는다.
- 검증 구간 분리: 단일 백테스트 자산곡선에서 만든 간이 점수를 OOS·purged CV·CPCV·PBO·DSR이라고 부르는 로직을 제거한다. 독립 증거가 없으면 승격을 차단한다.
- 연구 기능: 후보 생성·백테스트·설명용 피드백은 남긴다. 독립 검증 없는 후보를 자동 개선 성공이나 실거래 자격으로 포장하지 않는다.

통계 단위는 소수 비율이다. 표준편차는 표본 기준(ddof=1), 연환산은 명시한 주기를 사용한다. 일봉 엔진은 일봉 주기 검사를 거쳐 252를 사용하고 CAGR은 실제 경과 시간(365.25일/년)을 사용한다. Sharpe/Sortino의 기본 초과수익 기준은 0이며 시장 무위험금리를 조회하지 않는다. 주기를 알 수 없거나 분모가 없는 값은 0 반환 규약을 사용하므로 해당 값만으로 순위를 판단해서는 안 된다. `annualization_available`이 연환산 가능 여부를 표시한다. 손실 거래가 없는 손익비율을 임의의 10으로 만드는 코드는 제거하며 `profit_factor_available`로 분모 존재 여부를 구분한다. 미지원 기본값이던 quality/growth/value 펀더멘털 필드도 제거한다.

## 검증 실행

- 변경 전: `python -m pytest -q --disable-warnings` → 623 passed, 95 subtests passed in 131.04s.
- 실제 브로커 조회 전용 사전점검: 계좌 연결 성공, 카나리 실행 조건 미충족, `submitted_order=false`.
- 기존 실거래 전략 파일의 읽기 전용 자격 조회: `live_strategy_resolved=true`. 과거 문서의 ‘CHAMPION 없음’을 현재 계좌 상태로 단정하지 않는다. 이 조회는 현재 주문 승인·자금·실시간 시세 검증을 대신하지 않는다.
- 최종 소스 전체 회귀: `python -m pytest -q --disable-warnings --tb=short` → 802 passed, 95 subtests passed in 108.09s.
- 원본 로그 보존 재실행도 802 passed, 95 subtests passed(84.53초). 근거 파일은 `.omo/evidence/live-runtime-20260908/full-pytest.txt`이다.
- 임시 폴더 학습 실행: 후보·거절 보고서 저장, `accepted=0`, 독립 검증 지표 5개 누락 명시, `promoted_exists=false`, 주문 0건. 같은 자료 재실행은 중복 평가를 건너뛴다. 기존 승인 전략은 변경하지 않는다.
- 격리 PyInstaller 빌드 성공(213.9초), `package_audit` 결과 `[]` 및 종료 코드 0. `compileall`과 `git diff --check` 성공.
- 빌드 중 pandas 선택 의존성 `jinja2` 누락 경고가 있었다. 애플리케이션에서 Jinja/Styler/HTML 렌더링 사용은 검색되지 않았다. Windows 리소스 갱신 권한 재시도는 복구되어 최종 빌드가 성공했다.
- 새 EXE 수동 QA PASS: 도움말 0, 잘못된 명령 2, 정상 일봉 모의 진단 0(종목 선택 성공), 중복 시각 입력 2, 실거래 전략 파일 입력 2. 진단 모두 `submitted_order=false`, `network_client_constructed=false`. 전체 사례 및 기대/실제 결과는 `.omo/evidence/live-runtime-20260908/qa.md`에 있다.
- 일봉 제한은 백테스트·연환산 계산의 규칙이다. 일반 무주문 진단은 분봉을 읽을 수 있고, 이것을 일봉 연환산이나 실거래 적합성 검증으로 해석하지 않는다. 초기 진단 fixture 실패는 증거 생성기의 BOM·등록소 배열 직렬화 문제였으며 제품 코드 변경 없이 수정했다.
- LSP/ruff/basedpyright는 설치되어 있지 않아 해당 검사를 통과했다고 주장하지 않는다.

최종 독립 리뷰: 목표 APPROVE (`.omo/evidence/live-runtime-refactor-goal-review.md`), 코드 APPROVE/WATCH (`live-runtime-refactor-code-review.md`), 보안 APPROVE (`live-runtime-refactor-security-gate-review.md`), 맥락 APPROVE (`live-runtime-refactor-context-review.md`); 뒤 세 파일도 `.omo/evidence/`에 있다. 수동 QA PASS와 함께 5개 관점 검토를 마쳤다. 중간 실패·거절 기록은 삭제하지 않고 최종 결과와 구분했다.

## 새 패키지

검증 로그는 `.omo/evidence/live-runtime-20260908/`에 보존했다.

| 근거 | 파일 |
| --- | --- |
| 전체 회귀 | `full-pytest.txt` |
| 소스 문법·공백 | `source-checks.txt` |
| 패키지 개인정보 검사 | `package-audit.txt` |
| 빌드 재검증·배포 EXE와 동일 해시 | `pyinstaller-rebuild.txt`, `rebuild-hashes.txt` |
| 실제 계좌 조회·기존 전략 자격 조회 | `read-only-readiness.txt` |
| 최종 Python 파일 목록(226개) | `source-file-inventory.txt` |

기존 대상 폴더로 빌드를 재검증한 시도는 덮어쓰기 방지로 중단되었다(`pyinstaller-verification.txt`). 삭제·강제 덮어쓰기 없이 새 evidence 폴더로 다시 빌드했고 성공했다. 재검증 EXE와 아래 배포 EXE의 해시가 같다. 첫 빌드 성공과 이 중간 실패를 구분한다.

경로: `deploy-staging/live-runtime-20260908/NasdaqAutoTrader/NasdaqAutoTrader.exe`.

SHA-256: `A3C9D601E21289C4E00C8EA3D51626B37215386BDF605B5945BD803C7F6D2FA0`.

EXE 단독이 아니라 같은 폴더의 `_internal`과 설정 파일을 함께 유지해야 한다. 기존 `dist` 및 실행 중인 프로그램은 교체하거나 재시작하지 않았다. 인증정보는 새 패키지에 넣지 않았다. 실행 시 기존 AppData 설정을 읽을 수 있으므로 GUI 시작 전에 자동운영·LIVE 설정과 현재 승인을 확인해야 한다. 이 작업에서는 GUI 자동운영을 시작하지 않는다.

## 남는 제한

독립 코드 리뷰는 `APPROVE / WATCH`로 종료했으며 CRITICAL/HIGH 차단 사항은 없다(`.omo/evidence/live-runtime-refactor-code-review.md`). 아래 GUI 사유 번역 및 큰 백테스트 파일의 유지보수 경고는 남아 있다. 수동 QA는 `.omo/evidence/live-runtime-20260908/qa.md`에서 PASS로 종료했다.

검증된 LIVE 전략·현재 승인·현금·손실 한도·장 시간·실시간 시세·주문 대사 조건이 모두 필요하다. 짧은 과거 시세와 후보 점수만으로 내일 수익을 보장할 수 없다. 기존 KIS 일봉 조회 길이와 신규 종목의 짧은 이력은 연구 승격을 제한할 수 있으며 이를 가짜 시세로 채우거나 승인 기준을 낮추지 않는다.

새 거절 사유 `independent_validation_required`는 JSON 보고서와 README에 설명했지만 기존 GUI 사유 번역에는 아직 전용 문구가 없어 일반 안내로 표시될 수 있다. 주문 차단에는 영향이 없다. 실제 독립 검증·학습 최적화는 구현하지 않았으며, 현재 후보 연구를 수익성 검증 시스템으로 주장하지 않는다.
