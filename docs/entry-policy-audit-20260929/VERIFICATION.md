# 후속 작업 변경 범위와 검증 기록

2026-09-29. 이 문서는 이번 진입 정책 후속 작업만 구분한다. 기존 저장소의 76개 추적 파일 변경·미추적 파일·과거 배포본 삭제 상태를 이번 수정으로 합산하지 않았다. 커밋·staging·reset·동기화를 하지 않았다.

## 변경 목록

경로는 저장소 루트 기준이다. 별도 표시 없는 파일은 이번에 추가했다.

| 파일 | 이유·범위 |
|---|---|
| `nasdaq_auto_trader/entry_policy_experiment.py`, `entry_policy_experiment_models.py` | 오프라인 A/B/C, 동일 자료 양방향 점수, 완성 봉 단위 일반 신호 제한, 보호 판단 우선, 제출/체결 상태 분리 |
| `nasdaq_auto_trader/entry_comparison.py`, `entry_comparison_risk.py` | 공통 기존 체결·비용 엔진의 동일 1% 위험 비교, 숫자 변경 거부, 실제 no_trade·거부 사유 |
| `nasdaq_auto_trader/entry_comparison_inputs.py`, `entry_comparison_metrics.py` | 명시적 시각·수집 이후 미래 봉 거부, 고정 구간, 모의 체결과 판단 연결, 미실현/FX·완전 달력월 구분 |
| `nasdaq_auto_trader/entry_intraday_replay.py` | 이전 완성 일봉 지표와 새 5분 가격의 분리, 동일 엔진 보조 replay, 라벨 가정 명시 |
| `nasdaq_auto_trader/backtest.py`, `backtest_execution.py` **기존 파일 추가 수정** | 선택적 `max_total_position_pct` 체결 직전 재검사. 기본 None으로 기존 호출 동작 유지, 새 비교만 0.5 사용 |
| `nasdaq_auto_trader/research_readonly.py`, `research_readonly_contract.py` | KIS 고정 호스트 인증·조회 허용 목록, 주문·취소 전송 불가, 제한된 재시도·응답 크기·비밀정보 없는 오류 |
| `nasdaq_auto_trader/research_readonly_credentials.py` | 기존 GUI와 같은 자격증명 우선순위, 비공개 원장 외부 저장 위치 |
| `nasdaq_auto_trader/research_readonly_collect.py`, `research_readonly_history.py`, `research_readonly_minute.py` | 월별 체결 조회·누적 체결 집계, 일봉 페이지, 사건 기간 5분봉 및 시간대 대조 |
| `nasdaq_auto_trader/research_public_transport.py`, `research_public_bars.py`, `research_public_fx.py` | 인증 없는 공개 GET·일봉 달력·기업행위 메타데이터·ECB 참조환율 |
| `scripts/collect_entry_policy_data.py`, `collect_public_entry_data.py` | 일회성 조회 CLI, 앱 초기화/브로커 로드 회피, 기존 출력 덮어쓰기 금지 |
| `scripts/run_entry_policy_comparison.py` | 네트워크·하위 프로세스 차단, CSV 전용 비교, 기존 결과 덮어쓰기 금지 |
| `experiments/entry_policy/profile.json` | dry_run/offline 전용 A/B/C. 기존 손절·익절·수량·자금 한도를 공통 고정 |
| `tests/test_entry_policy_strategy.py`, `test_entry_policy_engine.py`, `test_entry_policy_fills.py` | 실제 엔진 최소매수 충돌, 강제 경로 비활성, 같은 봉/보호/부분·미체결 경계 |
| `tests/test_entry_comparison_cli.py`, `test_entry_comparison_limits.py`, `test_entry_comparison_metrics.py`, `test_entry_intraday_replay.py`, `test_entry_fill_exposure.py` | CLI 입력·출력·격리, 비교 지표·예산·체결 비중·완성 일봉/5분 가격 |
| `tests/test_research_readonly.py`, `test_research_readonly_boundaries.py`, `test_research_readonly_collect.py`, `test_research_public.py` | 전송 전 차단, 인증과 주문 구분, 데이터·시간·수수료 결측·파일 보존 |
| `docs/entry-policy-audit-20260929/`, `.omo/plans/entry-policy-audit-20260929.md` | 근거·동결 조건·실제 시세의 모의 결과·검증·독립 검토. 개인 계좌 원장 없음 |

이전 8%·10%·ATR 후보와 실거래 JSON, `.env`, EXE, 현재 보유분 정책, 일반 엔진·승인·종목별 보호·주문 중복 방지 코드는 이번에 수정하지 않았다. 공통 백테스터에는 위 선택적 검사만 더했다. 원본 해시가 없는 전체 작업 트리의 일괄 보존 증명이라고 주장하지 않고, 별도로 기록한 운영 파일 10개의 해시와 이전 후보 정의를 대조했다.

## 마지막 통합 회귀

Git Bash, 저장소 루트에서 실행. `scripts/run_offline_tests.py`는 기존 하네스이며 자격증명 환경 제거·네트워크 연결 거부·외부 pytest 플러그인 비활성화를 적용한다.

```bash
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_indicators_strategy.py tests/test_profit_protection*.py tests/test_auto_symbol*.py tests/test_automatic*.py tests/test_fixed_quantity_risk_limits.py tests/test_order_retry_safety.py tests/test_preorder_cycle_failure.py tests/test_daily_minimum*.py tests/test_daily_buy_objective.py tests/test_daily_forced_order_engine.py tests/test_forced_order_retirement.py tests/test_backtest_result.py tests/test_early_exit*.py tests/test_exit_experiment*.py tests/test_entry_policy*.py tests/test_entry_comparison*.py tests/test_entry_intraday_replay.py tests/test_entry_fill_exposure.py tests/test_research_readonly*.py tests/test_research_public.py
```

**555 passed, 29 subtests passed in 119.25s**, exit 0. [전체 원문](final-tests.txt). 이전 437개 실행이나 아래 독립 검토·집중 회귀를 이 숫자에 더하지 않는다. 전체 저장소 모든 테스트를 실행한 것은 아니다. 이후 수집 모듈의 린트 정리와 해당 집중 회귀는 별도 기록한다.

## 필수 동작의 증거

| 검증 | 실제 실행과 결과 |
|---|---|
| 낮은 점수·당일 0건 | 실제 TradingEngine dry-run + 실제 최소매수 함수에서 매수 점수 0→매수→5분 뒤 일반 매도 재현. minimum=false일 때 매수 없음 |
| 다른 정책 우회 | 폐기된 daily_forced true/false와 0/1개 보유 조합에서도 minimum 비활성 시 강제 진입 없음 |
| 매수·매도 충돌 | 같은 봉·동일 점수를 기록하고 C 신규 진입 거부. B는 원래 일반 신호 유지 |
| 동일 봉 반복 | C 일반 매수·매도 재사용과 반복 재진입 거부. 더 늦은 완성 봉에서만 해제 |
| 새로운 시세의 보호 | 일반 신호가 제한된 같은 봉에서도 새 유효 mark가 손절에 닿으면 보호 매도. 실제 5분 모의 결과 C hard stop 2건 |
| 미체결·부분 체결 | 접수만으로 1주 목표 완료·보유·실현손익으로 처리하지 않음. 실제 누적 체결과 제출 판단 분리 |
| 비용·현금·위험 | 앞선 qty=1·비용·예약·부분 청산 회귀 유지. 보유 가격 상승 뒤 추가 매수의 50% 초과를 실패 재현→체결 전 거부 |
| 조회·모의의 주문 차단 | 고정 KIS 조회 계약 외 order/cancel/hashkey 등 wire 전 거부. 공개 GET에 자격증명 없음. 모의 소켓·DNS·HTTP·자식 프로세스 접근 거부 |
| 자료 경계 | 날짜만 있는 CSV가 자정으로 바뀌어 통과하던 오류 재현→명시적 시각/시간대 요구. 수집 이후 미래 봉 거부 |
| 파일·설정 경계 | 기존 결과 폴더를 재사용하던 오류 재현→빈 폴더만 허용. dotenv 파일 내부 마지막 값/파일 간 GUI 우선순위 유지 |

## 직접 사용 및 독립 대사

실제 조회 CLI 두 번의 인증·제한된 페이지 조회는 [수집 명령](data-acquisition.md)에 기록했다. 공개 데이터 CLI 정상·도움말·잘못된 출력 경로는 [public-data.md](public-data.md)에 기록했다. 이들은 실제 읽기 요청이며 주문/취소는 없다.

비교 CLI의 `--help`, 합성 정상 실행, 실제 데이터 세 구간 실행, 잘못된 입력을 실행했다. [comparison-guide.md](comparison-guide.md)에 실제 전체 명령이 있다. 독립 QA는 최종 25개 잘못된 입력 시나리오를 CLI로 검증했고 기존 출력 바이트 보존을 확인했다. [QA 기록](review-qa.md), [최종 CLI 사례](qa/cli-cases-final.json).

실제 시장 자료 산출물 48개 조합(일봉 42+분봉 6), 모의 체결 276개를 대상으로 비용·현금·체결/판단 연결을 독립 대사했다. 일봉 평가액·월별/FX 계산, 분봉의 평가 시각 이전 일봉만 사용한 점도 검사했다. 실제 체결 원장은 이 공개 산출물에 포함하지 않았다.

추가된 50% 체결 검사는 산출물을 생성한 뒤 발견·수정했다. 기존 결과를 덮어쓰지 않았으며 정확한 체결 시점의 보유 노출을 다시 계산해 주 비교 최대 4.459228%, 보조 5.162681%, 분봉 5.946282%로 검사 임계값보다 작음을 확인했다. 거부만 추가하는 변경이므로 해당 결과의 변동이 없다는 근거이며 성과를 다시 맞춘 것이 아니다. [코드 검토의 계산 근거](review-code.md).

## 독립 검토와 남은 한계

| 검토 | 결과 | 문서 |
|---|---|---|
| 목표·안전 제약 | PASS | [review-goal.md](review-goal.md) |
| 코드·계산 | PASS, 체결 비중·원본 시각 결함 수정 후 | [review-code.md](review-code.md) |
| 보안·격리·정보 노출 | PASS, 출력 보존·dotenv 우선순위 수정 후 | [review-security.md](review-security.md) |
| 직접 CLI·독립 계산 | PASS | [review-qa.md](review-qa.md) |
| 실행본·근거·문맥 | PASS | [review-context.md](review-context.md) |

LSP는 설치되어 있지 않고 이전 설치 거절을 존중해 설치하지 않았다. 캐시된 일회성 basedpyright 검사에서 조회 모듈은 오류 0·경고 41개, 정책 모듈은 오류 0·경고 3개, 추가 체결 검사 범위는 오류 0·경고 19개였다. 서로 범위가 달라 합산하지 않는다. 전체 프로젝트 strict-clean이나 LSP 통과라고 쓰지 않는다.

실제 EXE·GUI 실행, 실주문·취소·실시간 체결·새 예약 작업은 수행하지 않았다. 실제 수수료·체결 시각, 당시 미완성 봉·학습 종목 순위·주문별 최종 설정, 분사 권리와 호가 대기열은 완전히 복원하지 못했다. PASS는 오프라인 구현과 제시한 제한 범위의 근거 확인이며 실거래 승인·수익성 보장이 아니다.

## 복귀와 적용 검토

마지막 전체 Ruff 검사에서 수집 모듈의 import/재수출·날짜 커서 관련 20건을 발견했다. 재수출은 `__all__`, 일봉 커서는 날짜 타입, 분봉 커서는 명시적 미국 시간대로 정리했다. 실제 시장자료를 다시 조회하지 않았다. 이후 아래 명령을 실행했다.

```bash
uvx --offline ruff check nasdaq_auto_trader/entry_policy_experiment*.py nasdaq_auto_trader/entry_comparison*.py nasdaq_auto_trader/entry_intraday_replay.py nasdaq_auto_trader/research_readonly*.py nasdaq_auto_trader/research_public*.py nasdaq_auto_trader/backtest.py nasdaq_auto_trader/backtest_execution.py scripts/run_entry_policy_comparison.py scripts/collect_entry_policy_data.py scripts/collect_public_entry_data.py tests/test_entry_policy*.py tests/test_entry_comparison*.py tests/test_entry_intraday_replay.py tests/test_entry_fill_exposure.py tests/test_research_readonly*.py tests/test_research_public.py
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_research_readonly*.py
python -m py_compile nasdaq_auto_trader/entry_policy_experiment*.py nasdaq_auto_trader/entry_comparison*.py nasdaq_auto_trader/entry_intraday_replay.py nasdaq_auto_trader/research_readonly*.py nasdaq_auto_trader/research_public*.py nasdaq_auto_trader/backtest.py nasdaq_auto_trader/backtest_execution.py scripts/run_entry_policy_comparison.py scripts/collect_entry_policy_data.py scripts/collect_public_entry_data.py
```

Ruff **All checks passed**, 집중 회귀 **28 passed in 3.26s**, 컴파일 exit 0. [최종 린트](final-lint.txt), [집중 회귀](final-focused-tests.txt). 이 28개는 위 555개와 중복되므로 합산하지 않는다.

최종 지정 운영 파일 10개의 hash가 모두 감사 시점과 일치했다([runtime-preservation.json](runtime-preservation.json)). 이전 조기매도 감사의 소스 hash 29개와도 대조했으며 이번 추가 수정인 `backtest.py`, `backtest_execution.py`만 달랐다([prior-work-preservation.json](prior-work-preservation.json)). 이전 후보 정의와 실험 비용 설정도 독립 검토에서 일치했다.

운영 연결이 없어 별도 설정 복귀 작업은 필요 없다. 새 비교 CLI 사용을 중단하면 된다. 기존 broader diff를 git reset/checkout하거나 배포본을 덮어쓰지 않는다. 선택적 백테스터 비중 검사는 호출 인자 생략 시 기존 None 동작이다. 향후 적용은 최소 매수 예외·완성 봉 상태 지속성·실시간 보호·실제 비용을 별도 검토하고 명시적으로 배포해야 한다.
