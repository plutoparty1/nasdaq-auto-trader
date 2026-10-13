# 80,000원 수익성 비교 검증 기록

**판단: 이번 비교에서 채택할 후보 없음.** 주 구간 최고 기본 비용 수익은 fixed8 위험1/2%의 +0.454407%이며, 각각 비용 스트레스에서 −1.489307%/−3.698495%다. 정수 HIVE1주 보유 기본 +1.704280%보다 낮다. 후보들의 완전월 +10%는 주0/4, 보조0/7·0/4·0/5다. [최종 보고서](REPORT.md)와 [전체96행 지표](results-tables.md)에 미실현손익·부분월 손실까지 포함했다. 테스트 통과는 수익성 입증이 아니다.

## 구현·보존 범위

기존 데이터 수집기와 공개 CSV, 비교 CLI, Backtester/ExecutionBook, 기존 C 및 ExperimentalExitStrategy, 비용·월별·거래 지표와 테스트를 재사용했다. 새 모듈은 오프라인 정책/위험/체결 어댑터, 프로필 검증, 지표/비교기준, 실험 실행, 기존 진단 및 저장 결과의 동시 조건 대사를 담당한다. 기존 파일 변경은 CLI의 선택 인자 `--profitability-profile`와 이 경로의 타입 명시뿐이다. 인자가 없으면 기존 A/B/C 실행 경로를 사용한다.

[최종 보존 대사](preservation-after.json): 시작 전890개 파일 중889개 바이트 동일, 누락0개. 변경1개는 `scripts/run_entry_policy_comparison.py`다. 비교 시작 당시 이미 미커밋이었던 소스·테스트·기존 보고서도 보존했다. 운영 설정·보유 종목 정책·EXE는 변경하지 않았다. 실주문·취소·예약·상주 실행·Git staging/commit을 하지 않았다. 개인 거래 원장은 수익성 증거로 읽거나 출력하지 않았다. 공개 연구 시세와 모의 체결만 사용했다.

프로필 SHA-256은 `69e6addc681961af86e2d08ca3f2188aa67ed5fe37dacefa234d86f31eff20a1`로 고정했다. 원본 전략/실험 설정·입력 시세·과거 환율 hash와 구간 경계도 검사한다. 출력 폴더가 비어 있지 않으면 거부한다. 네 정책×세 위험예산=12개이며, 비용/구간 반복을 합친96행을96개 탐색 후보로 세지 않는다.

## 실제 실행과 독립 대사

- 주 비교24행·보조72행을 계산 전 고정 규약으로 각각 한 번 실행했다. 두 실제 호출의 종료코드0 및 요약을 [main-run.txt](main-run.txt), [pair-run.txt](pair-run.txt)에 전사했다. 이 두 파일은 원시 stdout 캡처라고 주장하지 않는다. 결과를 보고 정책 숫자·기간·종목을 바꾸지 않았다.
- 기존 A/B/C24개 일봉 조합은 진단만 추가해 재생했다. [identity-check.json](identity-check.json)의 체결·평가액·거부·판단·진입 차단이 원본 전체 정밀도와 일치한다. 별도 intraday 원본도 대사표에 포함했다.
- QA가96개 결과의 현금·보유평가·수수료·가격 영향·실현/미실현손익·월별 수익·매도 사유를 CSV와 공개 OHLC로 독립 재계산했다. 1,620개 체결은 모두1주다. 반복 시나리오 체결을 독립 표본으로 합쳐 통계적 확신을 만들지 않았다.
- 합계 위험 추가 진단은 전략을 재실행하지 않았다. 보유·예약 위험을 시간순으로 별도 복원해 주7,871+보조19,947행이 일치했고, 실제 매수821건의 비용 포함 계획위험 및 체결위험 관계를 확인했다. 원래 first reason과 all blockers는 보존했다. 가상 추가1주의 동시 합계위험 초과와 실제 제출/체결 거부0건을 구분한다.
- [USD/KRW 목표 대사](target-currency-audit.json)는 두 통화의 월별 +10%가 모두0임을 확인했다. [배당 겹침 대사](dividend-overlap.json)는 후보96개·실행가능 보유8개에 기록된 배당 보유 자격 겹침0건, 분수 참고치의 누락 민감도를 별도 기록했다.
- QA는 실제 CLI로 `--help`, 합성 자료 배관 확인, 잘못된 입력17종, 출력 보존 등26개 시나리오를 수행했다. 명령별 종료코드/stdout/stderr는 [qa](qa/)에 있다. 합성 성과는 수익성 근거에서 제외했다.

## 런타임 가설과 관측

| 가설 | 실제 관측과 판정 |
|---|---|
| H1: A/B/C가 표시 반올림 때문에 같아 보인다 | 체결·평가 경로는 전체 자릿수까지 같았다. 다만 A의 추가 강제 주문1건은 제출 후 미체결이므로 주문 경로까지 모두 같다는 가설은 기각. |
| H2: 신호가 없거나 현금 부족이 작은 결과의 전부다 | 기존 주 기본 매수 차단 A345/B179/C162건 모두1주 위험>1%; 추가 강제 후보도167건 있었다. 현금/주문가능금액/$35 차단0건. 평균 투자0.105921%와 정수·위험 제한이 핵심. |
| H3: 위험1→2→4%가 거래 수량을 비례 확대한다 | 모든 체결1주. 주 기본 C2=C4, fixed8 1=2, fixed10 1=2=4는 전체 경로도 동일. 일부 새 진입은 허용됐으나 주 C1→2와 fixed8 2→4는 순성과 악화. |
| H4: 비용이 작은 수익을 소멸시킨다 | 기존 주 기본 gross+$0.020000에서 비용$0.032201 후 net−$0.012201. 신규 fixed8 1% 기본 gross+$0.570000/net+$0.245710, stress gross+$0.880000/net−$0.805310. 체결별 비용과 계좌 손익 대사 일치. |

## 발견 사항과 수정

1. 제출 수 집계에서 마지막 시점의 `end_of_data_unfilled`와 동일 시각 매도 거부를 매수 미제출로 오해할 수 있었다. 실제 제출/미제출을 구분하도록 최소 수정하고 관련 세 회귀 사례를 추가했다. 성과·체결 경로를 변경한 수정이 아니다.
2. 새 모드의 protocol/manifest가 옛 A/B/C 공통1% 제한 문구를 물려받았다. 새1/2/4% 비교의 설명으로 수정했다. 초기 JSON을 보존했고 [metadata-correction.json](metadata-correction.json)으로 변경을 기록했다. 수치 CSV30개 hash는 전부 그대로이며 전략 재실행은 없었다.
3. 단순 보유의 매수 시점은 후보 계산 전에 첫 평가 종가 다음 관측봉 시가로 바로잡고 규약에 기록했다. 알려지기 전 FX와 시작일 시가를 결합하지 않는다.

## 최종 회귀·정적 검사

최종 선택 회귀는 **220 passed, 4 subtests passed, 29.54초**. 앞선 부분 테스트 수를 더해 부풀리지 않았다. [실제 출력](final-tests.txt).

```bash
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_profitability*.py tests/test_entry_policy*.py tests/test_entry_comparison*.py tests/test_entry_intraday_replay.py tests/test_entry_fill_exposure.py tests/test_exit_experiment*.py tests/test_early_exit_backtest*.py tests/test_fixed_quantity_risk_limits.py tests/test_backtest_result.py
uvx --offline ruff check nasdaq_auto_trader/profitability*.py scripts/run_entry_policy_comparison.py tests/test_profitability*.py
uvx --offline basedpyright --pythonpath C:/Python314/python.exe nasdaq_auto_trader/profitability*.py scripts/run_entry_policy_comparison.py tests/test_profitability*.py
python -m py_compile nasdaq_auto_trader/profitability*.py scripts/run_entry_policy_comparison.py tests/test_profitability*.py
python /c/Users/u/.codex/plugins/cache/sisyphuslabs/omo/4.16.3/skills/programming/scripts/python/check-no-excuse-rules.py nasdaq_auto_trader/profitability*.py tests/test_profitability*.py
```

- [Ruff](final-lint.txt): All checks passed.
- [Basedpyright](final-types.txt): **0 errors, 131 warnings**. 사용한 Python 경로를 지정해 pytest 설치환경을 맞췄다. 경고는 기존 모형/argparse의 불명확 타입, override 표시, 내부 함수 재사용, 무시한 테스트 호출 반환값 등을 포함한다. 엄격한 타입 경고까지 전부 없다는 뜻은 아니다. 오류 억제 주석으로 숨기지 않았다.
- Python 컴파일 종료0. [구조 검사](structure-check.txt): 새 모듈/테스트16개에 위반0.

## 다섯 검토 경로

| 검토 | 최종 판정 | 증거 |
|---|---|---|
| 목표/사용자 제약 | PASS | [review-goal.md](review-goal.md) |
| 코드/수치·시간순 위험 | PASS | [review-code.md](review-code.md), 추가 동시 위험 대사 포함 |
| 보안/운영 격리 | PASS | [review-security.md](review-security.md), live 모듈/민감 파일 접근0 및 socket/subprocess 차단 실제 확인 |
| CLI 실제 사용/수치 QA | PASS | [review-qa.md](review-qa.md),26개 시나리오와 저장 출력 |
| 기존 맥락/자료 해석 | PASS | [review-context.md](review-context.md) |

각 검토에는 구조적 비판과 증거를 남겼다. 남은 차단 이슈는 없다. 이는 오프라인 코드와 계산의 검증이며 거래 승인이나 독립 수익성 검증이 아니다.

## 재현과 남는 한계

저장소 루트의 실제 Git Bash에서 실행한다. 새 빈 출력 경로를 전달한다.

```bash
bash docs/profitability-80000-20261011/reproduce.sh NEW_EMPTY_OUTPUT_PARENT
```

[재현 스크립트](reproduce.sh)는 기존 CLI의 원래 공개 데이터 경로·환율 자료·경계·별도 프로필을 고정한다. 원본 시세/FX와 프로필이 현재 hash와 같아야 실행되며 결과 디렉터리 덮어쓰기를 거부한다. [프로필](../../experiments/profitability_80000/profile.json)은 offline_csv와 dry_run 설정이다. 손절 숫자·위험·종목·기간을 더 바꾸는 후속 탐색이나 실거래 승격은 하지 않는다.

새 독립 자료가 없어 전부 탐색 비교다. 실제 KIS 주문/잔량/부분체결, 당일 고저 순서와 장중 손절 감시, 실제 계좌 수수료·과거 부과금·환전 비용·세후 배당·운영비를 검증하지 않았다. EXE/GUI는 실행하지 않았다. 기존4거래일 분봉 증거를12후보 장중 수익성 검증이나 월/연 기대수익으로 확대하지 않는다. 이 한계 때문에0거래나 작은 표본을 안정적인 전략이라고 부르지 않는다.
