# 진입 정책 A/B/C 오프라인 비교

이번 비교는 실거래 실행본의 전체 성과 재현이 아니다. A는 일일 최소 매수에 의한 HOLD→BUY 승격을 재현하는 **동일 위험 한도의 오프라인 대리 기준선**이다. 당시 일일 최소 매수의 거래당 위험 5% 덮어쓰기는 제외하고 A/B/C 모두 통상 위험 1%를 적용한다. 이를 달리 적용하면 진입 정책과 위험 예산을 동시에 바꾸게 된다. 실제 당시 5% 경로의 동작 재현은 가짜 브로커를 사용하는 엔진 회귀에서만 수행한다. 일봉 비교와 실제 분봉 자료 비교는 모두 동일한 1% 위험 한도이며 당시 5% 운용 수익의 재현이 아니다.

## 바뀌는 항목과 고정한 항목

| 정책 | 신규 진입 정책 | 기존 청산 규칙 |
|---|---|---|
| A | 미국 거래일에 실제 매수 체결 1주를 채우지 못했으면 유효 HOLD를 강제 진입 후보로 변환 | 공통 |
| B | 강제 승격 없음. 매수 0건은 정상 no_trade | 공통 |
| C | B + 같은 데이터의 매도 점수가 4 이상이면 신규 매수 거부 + 이미 평가한 완성 봉의 일반 신호 재사용 차단 | 공통 |

A의 후보 순서는 공통 백테스터의 종목 알파벳 순서다. 당시 학습 종목 선정·best-affordable 순서를 복원한 것이 아니다. 최초로 위험 검사에서 주문 후보가 승인되면 같은 평가 시각에 다른 강제 후보를 만들지 않는다. 주문 접수만으로 실제 체결 목표를 달성했다고 보지 않는다. 미체결 주문은 보유·실현손익이 아니며 후속 평가에서 다시 후보가 될 수 있다.

고정값은 초기 80,000원, 거래당 위험 1%, 정수 1주, 주문 상한 $35, 종목당/총 노출 50%, 현금 여유 5%, 일일 계좌손실 2% 도달 시 신규 매수 중단이다. 별도 월간 손실 제한이나 총 초기 위험 6%를 이번에 추가하지 않았다. 고정 손절 3%, 익절 5%, 일봉 ATR(14) 손절×3/익절×5, 트레일링 활성 2%/하락 1% 및 `corrected_exits=false`를 모두 동일하게 보존한다. 이전 8%·10%·진입 ATR 후보 파일은 수정하지 않았다.

위험거리는 기존 보수적 `max(고정 손절 거리, ATR 거리)`에 예상 왕복비용을 더한다. 가장 먼저 발동하는 손절선과 동일한 값이라는 뜻은 아니다. 1주도 비용 포함 1%를 초과하면 거부한다. 이 제약 때문에 CMCSA·KDP 진입 후보 대부분이 체결되지 않을 수 있으며 결과를 보고 완화하지 않았다.

일반 신호는 완성 일봉 기준이다. C에서도 새로운 유효 평가가격에 의한 고정/ATR/트레일링 보호 판단을 먼저 수행한다. 이 CLI의 일봉 실행만으로 반복 5분 조회 차단이나 실제 5분 보유시간을 입증하지 않는다. 해당 동작은 별도 반복 평가 테스트·분봉 replay에서 확인한다.

## 데이터와 사전 고정

[원래 계획](comparison-frozen-plan.json)은 실제 시세 성과 계산 전에 A/B/C·비용·위험·구간을 고정했다. 학습 구간 종료는 2025-08-29, 검증 종료는 2026-02-27, 최종 구간은 2026-03-02~09-28이다. 모든 종목에 64개 봉을 준비 이력으로만 쓰고 이후부터 주문을 평가한다. 매 구간은 8만원 상당에서 독립 시작하며 최종 결과에 따라 수치를 조정하지 않았다.

Yahoo 공개 일봉은 종목별 519개, 2024-09-03~2026-09-28이다. CMCSA의 2026-01-05 Versant 분사 때문에 이전 가격에 조정 정보가 반영된다. 공급자의 1067:1000 표기를 단순 주식 수 분할로 해석하지 않았다. 분사 권리·단주 현금 정산을 구현하지 않았으므로 **어떤 실제 전략 수익도 계산하기 전에** [데이터 품질 변경 기록](comparison-frozen-amendment.json)을 남겼다.

- 주 비교: 세 종목 모두 2026-01-06 이후 183개 봉만 사용. 64개 준비 봉 이후 **2026-04-09~09-28**을 평가한다. 기존 학습·검증 종료일은 이동하지 않아 두 구간은 자료 부족으로 생략된다. 학습한 모델의 독립 최종 평가라고 주장하지 않는다.
- 보조 비교: 해당 분사 조정이 없는 KDP/HIVE 두 종목의 519개 봉, 원래 세 구간을 유지한다. 다른 종목군 결과를 주 비교와 합쳐 진입 정책 효과라고 계산하지 않는다.
- 별도 SPY 대조: 519개 봉과 같은 세 구간. 8만원·1주·$35 한도 때문에 매수할 수 없으면 그대로 거래 0건이다.

미국 거래일 달력 및 조기 폐장 시각을 적용한 UTC 일봉 종료시각이며 검증 달력상 결측률은 0이다. 배당 현금은 제외하고 Yahoo quote OHLC를 사용한다. `adjclose`를 사용하지 않았다. 원시 공개 자료·원천 manifest와 환율은 `%LOCALAPPDATA%/NasdaqAutoTrader/research/entry-policy-20260929/public/`에 있다. 보고서 안의 fills.csv는 실제 시장 자료로 계산한 **모의 체결**이며 개인 계좌 원장이 아니다.

환율은 ECB의 KRW/EUR ÷ USD/EUR 기준환율 530개를 사용한다. 관측 당시 이용 가능한 마지막 값만 적용한다. 실제 환전 체결가격·스프레드는 아니다. 원화 평가액에는 달러 현금의 환율 손익도 포함된다. 주 비교 시작 FX 기준 $54.07 상당이 8만원이며 원화 하락의 대부분은 환율 영향이다.

## 실제 시장 자료 비교 결과

주 비교, 2026-04-09~09-28. 아래 수치는 모의 체결과 미실현 평가손익을 포함한다.

| 정책/비용 | 매수 조건 미충족 체결 | 다음 일봉 평가 일반 매도 체결 | 완결 거래 | 거래비용 USD | USD 순수익률 | KRW 순수익률 | USD 최대낙폭 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A / 기본 | 0 | 0 | 2 | 0.032201 | -0.022564% | -8.237002% | -0.515469% |
| B / 기본 | 0 | 0 | 2 | 0.032201 | -0.022564% | -8.237002% | -0.515469% |
| C / 기본 | 0 | 0 | 2 | 0.032201 | -0.022564% | -8.237002% | -0.515469% |
| A/B/C 각각 / 불리한 비용 | 0 | 0 | 0 | 0 | 0% | -8.216293% | 0% |

주 비교 기본 비용의 실현손익은 각각 -$0.012201, 기말 미실현손익은 반올림상 0, 평균 보유기간은 **일봉 라벨 간격 기준 36시간**이다. 이는 실제 장중 체결시각 기반 보유시간이 아니다. 4~9월 관측창의 최악 월은 -0.022564%이며, 완전한 달력월인 5~8월의 월 +10% 횟수는 **0/4**다. 첫 4월과 마지막 9월은 부분 월이다.

A에서 강제 진입 후보는 기본 비용 167건 발생했지만 조건 미충족 매수 체결은 0건이다. 실제 자금·1주·위험 한도가 먼저 막아 정책 차이가 체결로 나타나지 않았다. 이 결과는 진입 교정의 수익 개선 증거가 없다.

보조 KDP/HIVE 비교의 최종 구간(2026-03-02~09-28)은 아래와 같다. 주 비교와 종목군·시작일이 다르다.

| 정책/기본 비용 | 미충족 진입 체결 | 다음 평가 일반 매도 | 완결 거래 | 비용 USD | USD 순수익률 | 최대낙폭 |
|---|---:|---:|---:|---:|---:|---:|
| A | 8 | 7 | 13 | 0.197949 | -0.105909% | -1.096930% |
| B | 0 | 0 | 5 | 0.080380 | -0.439327% | -0.955031% |
| C | 0 | 0 | 5 | 0.080380 | -0.439327% | -0.955031% |

강제 진입·짧은 일반 청산·비용은 줄었지만 **최종 순수익은 B/C가 A보다 나빴다**. 학습 구간에서는 B/C가 A보다 나았고 검증 구간에서는 A보다 나빴으므로 개선이 일관되지 않았다. 최종 구간의 불리한 비용에서는 모두 체결 0건이다. 거래 수 감소나 현금 보유를 수익성 향상으로 해석하지 않는다. 별도 SPY 대조도 모두 거래 0건으로 전략 성과 검증 불가다.

모든 월별 값, 사유별 손익과 비용은 [주 비교](actual-main/summary.csv), [월별](actual-main/monthly.csv), [사유별](actual-main/reasons.csv), [보조 비교](actual-no-action-pair/summary.csv), [SPY 대조](actual-spy-control/summary.csv)에 남겼다. `complete_calendar_months`와 `target_complete_calendar_months`가 부분 월을 제외한 기본 지표다. 기존 `evaluated_months`/`target_months`는 부분 월을 포함한 관측창이므로 완전한 월 표본으로 혼동하지 않는다. 과거 관측 빈도는 미래 달성 확률이 아니다.

## 비용·체결·안전 한계

기본 비용은 편도 수수료 0.25%, 최소 $0 가정, 전체 스프레드 10bp, 추가 편도 슬리피지 10bp다. 불리한 비용은 0.30%, 최소 $0.10, 스프레드 30bp, 슬리피지 30bp다. 모두 기존 사전 정의 가정이며 실제 계좌 청구액으로 확정하지 않는다. 데이터·서버·AI 운영비는 확인되지 않아 빈 값이고 0원으로 가정하지 않는다. `--monthly-operations-krw`로 확인된 금액을 별도 차감할 수 있다.

수정된 공통 `Backtester`가 신호 이후 다음 일봉에서 지정가 도달 여부와 비용·현금 예약·위험을 검사한다. 지정가는 미도달하면 DAY 미체결이다. 실제 호가 대기열·유동성·분봉 순서·배당·분사 권리는 재현하지 않는다. 한 일봉에서 손절·익절을 모두 통과한 순서는 알 수 없다. 보호는 관측 종가 기준이며 장중 실시간 감시와 다르다. 체결의 timestamp는 해당 일봉 라벨이므로 실제 체결시각이 아니다.

CLI는 실제 앱 초기화·환경설정·브로커 모듈을 로드하지 않는다. 소켓과 하위 프로세스 실행을 audit hook으로 거부하며 직접 회귀에서 차단을 확인했다. 실제 주문·취소 API 호출은 0건이다. 운용 JSON·보유 정책·EXE·예약 실행은 변경하지 않는다. CSV와 실험 프로필만 사용한다.

## 실행·출력·되돌리기

```text
python scripts/run_entry_policy_comparison.py --help
python scripts/run_entry_policy_comparison.py --synthetic-smoke --output FRESH_EMPTY_DIRECTORY --usdkrw 1400 --fx-source synthetic-assumption-not-market-rate --fx-as-of 2020-01-01
```

합성 명령의 환율은 실제값이 아니며 결과는 재현 검증 전용이다. 실제 주 비교에서 실행한 명령은 다음과 같다. 기존 출력 폴더는 재사용하지 않는다.

```text
python scripts/run_entry_policy_comparison.py --bars C:/Users/u/AppData/Local/NasdaqAutoTrader/research/entry-policy-20260929/public/actual_trade_group_after_corporate_action.csv --provenance C:/Users/u/AppData/Local/NasdaqAutoTrader/research/entry-policy-20260929/public/comparison-provenance.json --output docs/entry-policy-audit-20260929/actual-main --usdkrw 1333.6339857490755 --fx-source ECB-reference-KRW-per-EUR-divided-by-USD-per-EUR --fx-as-of 2024-08-30T16:00:00+00:00 --fx-history C:/Users/u/AppData/Local/NasdaqAutoTrader/research/entry-policy-20260929/public/usdkrw.csv --train-end 2025-08-29T23:59:59+00:00 --validation-end 2026-02-27T23:59:59+00:00
```

보조 비교는 `--bars .../actual_trade_group.csv --action-free-pair --output .../actual-no-action-pair`, SPY는 `--bars .../SPY.csv --control --output .../actual-spy-control`로만 바꾸고 나머지 인자는 동일했다. 각 실행은 exit 0이었다. 각각의 protocol.json은 계산 전에 저장되고 설정·데이터 해시를 포함한다. 출력은 summary/monthly/fills/reasons/equity/decisions/entry_skips/order_rejections CSV다.

이 실험은 운영 경로에 연결하지 않았으므로 기존 운영으로 되돌리는 설정 조작이 필요 없다. 별도 CLI 사용을 중단하면 된다. 다른 작업의 미커밋 변경을 포함하는 git reset·checkout·배포본 덮어쓰기를 하지 않는다. 실거래 검토는 이 제한된 결과, 실제 수수료·분사 처리·체결 대사·현재 보유 정책을 확인한 뒤 별도로 진행해야 한다.

## 검토 중 보완한 안전 경계

빈 디렉터리만 출력으로 허용한다. protocol.json이 없어도 기존 파일이 하나라도 있으면 라이브러리와 CLI 모두 거부한다. 합성 입력은 임시 디렉터리에 만들고 계산이 끝난 뒤 새 출력 폴더에 복사한다. 실제 이력 CSV는 날짜만 있거나 시간대가 없는 원본 timestamp를 거부한다. 정규화 이전에 명시적 UTC offset과 수집시각을 검증하고 수집 이후의 미래 봉을 거부한다.

최종 검토에서 공통 체결 엔진의 선택적 체결 시 총노출 재검사를 .5로 연결했다. 제출 이후 갭·수수료·잔여 미체결 예약으로 노출을 넘으면 체결을 거부한다. 독립 검토에서 기존 실제 자료 산출물의 최대 노출은 주 비교 4.459%, 두 종목 보조 5.163%로 50%보다 작아 기존 결과에 영향이 없음을 확인했다. 결과를 보고 위험 한도나 전략 조건을 다시 조정하지 않았다.

## 이 하위 작업의 검증 기록

```bash
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_entry_comparison*.py
uvx --offline ruff check nasdaq_auto_trader/entry_comparison*.py scripts/run_entry_policy_comparison.py tests/test_entry_comparison*.py
python -m py_compile nasdaq_auto_trader/entry_comparison.py nasdaq_auto_trader/entry_comparison_inputs.py nasdaq_auto_trader/entry_comparison_metrics.py nasdaq_auto_trader/entry_comparison_risk.py scripts/run_entry_policy_comparison.py
```

최종 집중 회귀는 **13 passed in 10.59s**, Ruff 전부 통과, 명시 파일 컴파일 exit 0이다. [원문](comparison-tests.txt). 재실행·이전 단계 테스트를 합산하지 않았다. Python 구조 검사도 신규 8개 파일에서 위반 0건이다. 전체 저장소·LSP 타입 검사 통과를 주장하지 않는다.

직접 CLI 실행으로 도움말, 18행 합성 비교, NaN 환율 거부, 날짜만 있는 원본 시세 거부를 확인했다. 날짜-only 입력은 명시적 시간대 오류 exit 1, protocol 미생성이었다. 합성 CLI 테스트는 독립 프로세스에서 소켓·하위 프로세스 차단과 실제 엔진/설정/KIS 모듈 미로드를 검사한다. 출력 파일 덮어쓰기 문제와 boolean 수량 입력 문제는 실패를 먼저 재현한 뒤 회귀가 통과했다.

| 신규 파일 | 역할 |
|---|---|
| `nasdaq_auto_trader/entry_comparison.py` | 공통 엔진 A/B/C 실행, 고정 프로필 검증, 계산 전 protocol 저장, 모의 결과 출력 |
| `nasdaq_auto_trader/entry_comparison_inputs.py` | 원본 timestamp·수집시각 검증, 64봉 준비와 고정 구간, FX·합성 입력 |
| `nasdaq_auto_trader/entry_comparison_risk.py` | 모든 후보의 동일한 기존 수량·가격·계좌 위험 한도, 일일 신규매수 중단과 보호 매도 분리 |
| `nasdaq_auto_trader/entry_comparison_metrics.py` | 주문 대신 모의 체결 연결, 조건 미충족/다음 평가 청산, 실현·미실현, 부분 월 구분 |
| `scripts/run_entry_policy_comparison.py` | 네트워크·하위 프로세스·실거래 초기화가 격리된 CSV CLI |
| `tests/test_entry_comparison_cli.py`, `test_entry_comparison_limits.py`, `test_entry_comparison_metrics.py` | 실제 CLI 안전 경계·동일 위험·timestamp·원장 계산 회귀 |

진입 정책 래퍼와 그 별도 회귀, 실제 엔진 경로·KIS 조회·분봉 replay의 검증 건수는 각 담당 보고서에서 확인한다. 이 13건과 다른 보고서 건수를 합쳐 고유 테스트 수라고 표시하지 않는다.
