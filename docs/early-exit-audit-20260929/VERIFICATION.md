# 수정 범위와 최종 검증

2026-09-29. 현재 로컬 소스의 오프라인 검증 결과다. 배포 EXE 재생성, GUI 실행, 주문·취소, 예약 작업, 승인 변경 및 실거래 전환을 수행하지 않았다. 전체 저장소에는 작업 전부터 많은 미커밋 변경이 있었다. 아래 목록만 이번 작업의 변경으로 분류하며 기존 변경 전체를 이번 수정이라고 주장하지 않는다.

## 변경 파일과 이유

경로는 저장소 루트 기준이다.

| 파일 | 변경 이유와 적용 범위 |
|---|---|
| `nasdaq_auto_trader/strategy.py` | 비정상 판단 가격 차단. 명시적 교정 모드에서 무효 ATR 제외 및 활성 트레일링 유지. 기존 유효 수치와 기본 정책 보존 |
| `nasdaq_auto_trader/strategy_config.py` | `corrected_exits=False` 기본값으로 정책 교정의 명시적 선택 구분 |
| `nasdaq_auto_trader/engine_cycle.py` | 일반 매도에서 불필요한 매수가능금액 API 의존 제거, 기존 승인·계좌·보유·중복 방지 경로 유지, 판단 진단 추가 |
| `nasdaq_auto_trader/exit_diagnostics.py` | 가격 출처·시각 결측, 두 점수, 고정/ATR/트레일링 임계값, 설정 해시를 제한된 필드로 기록. 선택적 지표 오류가 보호 결과를 덮지 않도록 처리 |
| `nasdaq_auto_trader/app_format.py` | 기존 GUI 로그 형식에 위 진단 객체 추가 |
| `nasdaq_auto_trader/experimental_exit.py` | 오프라인 fixed/entry-ATR 선택, 최초 체결 손절 고정, 일반 신호와 하드 보호 분리 |
| `nasdaq_auto_trader/experimental_exit_models.py` | 비율 단위·정책·상태 계약 검증, 지원하지 않는 legacy+비상손절 조합 거부 |
| `nasdaq_auto_trader/experimental_exit_state.py` | 진입 ATR, 초기/비상 손절, 보유 최고가, 활성 상태의 v2 저장·복원 및 설정 지문 확인 |
| `nasdaq_auto_trader/experimental_exit_diagnostics.py` | 실험의 실제 유지 손절과 추적 보호를 표시 |
| `nasdaq_auto_trader/backtest.py` | 기존 CSV 백테스터의 시간순 처리, 신호/다음 봉 체결 분리, 보유 이후 관측 최고가 갱신 |
| `nasdaq_auto_trader/backtest_costs.py` | 수량 단위·지정가·수수료·최소 비용·스프레드·슬리피지 |
| `nasdaq_auto_trader/backtest_execution.py` | qty 매수, 현금·위험 예약, 갭 재검사, 추가 매수 평균가·부분 매도·체결 상태 통지 |
| `nasdaq_auto_trader/backtest_types.py` | 비용·거절·잔여 포지션·체결 관찰자 계약; 기존 결과 import 유지 |
| `nasdaq_auto_trader/exit_experiment.py` | 사전 고정 후보, 시계열 구간, 공통 엔진 비교, 불변 protocol 및 결과 CSV |
| `nasdaq_auto_trader/exit_experiment_config.py` | offline/dry_run, 8만원, 비용·데이터 출처·단위 검증 |
| `nasdaq_auto_trader/exit_experiment_risk.py` | 1주/동일 위험예산 수량, 2%/4%·현금·비중·총 위험·월 손실 신규매수 중단 |
| `nasdaq_auto_trader/exit_experiment_metrics.py` | 미실현 포함 평가액, USD/KRW·월별·완결 거래·사유·비용·운영비 지표 |
| `scripts/run_exit_experiments.py` | 실제 앱 초기화와 브로커를 로드하지 않는 CSV CLI, 소켓/자식 프로세스 차단 |
| `scripts/run_offline_tests.py` | 자격증명 환경 제거, 소켓 연결 차단, 외부 pytest 플러그인 자동 로드 중단 |
| `experiments/early_exit/settings.json`, `profiles.json`, `provenance.example.json` | 기존 실거래 파일과 분리된 실험 한도·5개 후보·필수 데이터 출처 예시 |
| `tests/test_early_exit_backtest.py`, `test_early_exit_backtest_edges.py`, `test_early_exit_backtest_safety.py` | 수량·비용·지정가·평균가·잔량·최고가·예약·갭·다음 봉 회귀 |
| `tests/test_early_exit_strategy_experiment.py`, `test_early_exit_strategy_guards.py` | ATR 중복·무효값, 신호 충돌, 트레일링 급락/재시작, 추가 체결의 유지 손절·위험 일치 |
| `tests/test_early_exit_diagnostics.py`, `test_early_exit_engine_safety.py` | 일반 실행 경로의 보호·매수능력 장애·진단 실패·중복 주문 차단 |
| `tests/test_exit_experiment_cli.py`, `test_exit_experiment_metrics.py`, `test_exit_experiment_risk.py` | CLI 격리·입력 경계·단위·계좌 평가액·FX·월 손실·위험예산 |
| `docs/early-exit-audit-20260929/`, `.omo/plans/early-exit-audit-20260929.md` | 근거·명령·결과·독립 검토·합성 산출물·작업 기록 |

`ai_quant_lab` 학습 백테스터, HIVE 전용 매도 모니터, 기존 실거래 JSON/환경/승인 파일은 이번 수정 대상이 아니다. 이 경로에 이미 존재한 미커밋 변경을 보존했다. 소스 수정은 현재 배포 EXE의 변경을 의미하지 않는다.

## 실제 실행한 최종 명령

Git Bash, 저장소 루트에서 실행했다. 회귀 하네스는 실제 네트워크 연결을 거부한다. 실제 KIS·Alpaca 주문 API는 사용하지 않았다.

```bash
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_indicators_strategy.py tests/test_profit_protection*.py tests/test_auto_symbol*.py tests/test_automatic*.py tests/test_fixed_quantity_risk_limits.py tests/test_order_retry_safety.py tests/test_preorder_cycle_failure.py tests/test_daily_minimum*.py tests/test_daily_buy_objective.py tests/test_daily_forced_order_engine.py tests/test_forced_order_retirement.py tests/test_backtest_result.py tests/test_early_exit*.py tests/test_exit_experiment*.py
```

**437 passed, 29 subtests passed in 93.40s**, exit 0. [원문 결과](final-tests.txt). 주문 승인·일일 최소 매수·보호 매도·중복/미체결·자동선정의 기존 관련 회귀도 포함한다. 저장소의 모든 테스트를 실행했다는 뜻은 아니다.

```bash
uvx --offline ruff check nasdaq_auto_trader/backtest*.py nasdaq_auto_trader/experimental_exit*.py nasdaq_auto_trader/exit_experiment*.py nasdaq_auto_trader/exit_diagnostics.py scripts/run_exit_experiments.py scripts/run_offline_tests.py tests/test_early_exit*.py tests/test_exit_experiment*.py
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_early_exit*.py tests/test_exit_experiment*.py
```

최종 import 형식 점검에서 신규 파일 4개의 I001 6건을 정리한 뒤 Ruff **All checks passed**, 집중 회귀 **91 passed in 7.50s**, exit 0. [린트](final-lint.txt), [집중 회귀](final-focused-tests.txt). 위 437개와 91개는 중복을 포함하므로 합산하지 않는다. 기능 변경 없이 import 정리만 마지막에 수행했다.

```bash
python -m compileall -q nasdaq_auto_trader/backtest.py nasdaq_auto_trader/backtest_costs.py nasdaq_auto_trader/backtest_execution.py nasdaq_auto_trader/backtest_types.py nasdaq_auto_trader/experimental_exit.py nasdaq_auto_trader/experimental_exit_state.py nasdaq_auto_trader/experimental_exit_models.py nasdaq_auto_trader/experimental_exit_diagnostics.py nasdaq_auto_trader/exit_experiment.py nasdaq_auto_trader/exit_experiment_config.py nasdaq_auto_trader/exit_experiment_metrics.py nasdaq_auto_trader/exit_experiment_risk.py nasdaq_auto_trader/exit_diagnostics.py nasdaq_auto_trader/strategy.py nasdaq_auto_trader/strategy_config.py nasdaq_auto_trader/engine_cycle.py nasdaq_auto_trader/app_format.py scripts/run_exit_experiments.py scripts/run_offline_tests.py
```

컴파일 exit 0. LSP 서버는 미설치이며 도구가 이전 설치 거부를 알려 추가 설치하지 않았다. 별도 임시 basedpyright CLI의 실험 모듈 8개 결과는 **오류 0, 경고 212**다([원문](experiment-types.json)). 전체 수정 파일의 타입 검사나 LSP가 깨끗하다고 주장하지 않는다.

## 재현 후 수정과 직접 사용 검증

- 백테스터: 최초 qty 매수·추가 매수·보유 최고가 3개 실패 → 수정 후 통과. 지정가/비용/예약 및 비용 위험 누락도 각각 실패를 먼저 확인했다. [상세 명령](backtest-fix.md).
- 일반 엔진: 매수가능금액 조회 장애가 매도까지 막는 실패 → 조회를 매수에 한정 후 통과. 진단 지표 예외가 이미 처리된 보호 주문 결과를 덮는 실패 → 제한된 지표 오류 처리 후 통과. [코드 검토](review-code.md), [실행 경로 재현](exit-audit.md).
- 실험 전략: 추가 체결 시 새 손절을 가정하는 위험 불일치, 평균가 변화로 비상 손절이 이동하는 문제, 지원하지 않는 legacy 비상손절 조합을 재현한 뒤 유지 손절·v2 상태·입력 거부로 수정했다. [전략 근거](strategy-fix.md).
- 일반 CSV CLI를 격리된 프로세스에서 직접 실행: qty=1, 다음 봉 체결, 7개 모의 체결, exit 0. 독립 unittest 경로의 기존 CSV/GUI 로직 6개도 통과했다. GUI 창이나 실거래를 실행한 결과는 아니다.
- 오프라인 실험 CLI의 도움말·정상 실행·잘못된 입력을 직접 실행했다. 기본 5개 후보는 **120행**, 선택적 진입 실험 2개 포함은 **168행**의 비교 결과를 생성했다. 모두 합성 자료이며 실제 시장 수익 검증 결과가 아니다.

```bash
python scripts/run_exit_experiments.py --help
python scripts/run_exit_experiments.py --synthetic-smoke --output docs/early-exit-audit-20260929/qa-review/smoke-final --usdkrw 1400 --fx-source "TEST ONLY final fixed FX assumption" --fx-as-of 2020-01-01 --compare-entry-gate
```

위 명령은 이미 실행한 기록이다. 재실행은 새 출력 폴더를 사용해야 한다. 완료 protocol 덮어쓰기는 의도적으로 거부한다. USD/KRW 1,400은 시험용 가정이며 실제 조회 환율이 아니다.

독립 QA는 CLI 경계 27개, 산출물 대조 5개, 관련 회귀 83개를 실행하여 **115 passing executions**를 기록했다. 168행 모두에서 현금·1,460개 모의 체결의 비용·16,800개 평가 기록·월별 수익을 별도로 재계산했다. 예산 초과 1,056개 건너뛰기와 거래가 없는 22개 조합을 그대로 보존했다. [QA 명령·26개 시나리오](review-qa.md), [합성 월별 파일](qa-review/smoke-final/monthly.csv), [합성 비교표](qa-review/smoke-final/summary.csv).

## 독립 검토와 한계

| 검토 | 최종 결과 | 근거 |
|---|---|---|
| 요구사항·안전 경계 | PASS | [review-goal.md](review-goal.md) |
| 코드·계산 일관성 | PASS, 발견한 3개 차단 문제 수정 후 재검증 | [review-code.md](review-code.md) |
| 브로커 격리·비밀정보·기존 승인 경로 | PASS | [review-security.md](review-security.md) |
| 실제 CLI 사용·독립 계산 | PASS | [review-qa.md](review-qa.md) |
| 로컬 근거·문서·실행 경로 | PASS | [review-context.md](review-context.md) |

이 PASS는 오프라인 소프트웨어 검증이다. 실제 체결 20~30건 분석, 실제 계좌 수수료/최소액, 당시 환율, 과거 종목 선정과 시장 국면별 전략 비교는 자료 부족으로 완료했다고 주장할 수 없다. 일봉 종가의 보호 판단은 실시간 손절과 같지 않으며 장중 순서·호가 대기열·부분 체결 확률을 재현하지 않는다. 실제 계좌 조회나 배포 EXE의 내부 바이트코드 대조도 하지 않았다.

일일 매도 제한·선정 실패·종목별 보호·승인 제약의 자동 청산 정책은 이번에 변경하지 않았다. 현행 일일 최소 매수 요구도 보존했다. 과거 수익 우열과 월 +10% 근거가 없다는 결론, 추가로 필요한 데이터와 실행 절차는 [최종 보고서](REPORT.md)와 [실험 안내](experiment-guide.md)에 명시했다.
