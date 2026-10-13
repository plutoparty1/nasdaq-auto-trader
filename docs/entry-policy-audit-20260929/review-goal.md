# 진입 정책 후속 작업 — 목표·제약 독립 검토

검토일: 2026-09-29. 검토 범위는 새 진입 실험·비교·조회 수집기와 실제 생성 산출물이다. 검토자는 이 문서만 작성하며 제품 코드·설정·EXE를 변경하지 않았다.

**판정: PASS — 검토 범위의 목표·제약을 충족하며 남은 차단사항은 없다.** 실제 일봉·분봉 비교 산출물과 마지막 체결 한도·출력 보존·인증정보 우선순위 보완까지 확인했으며 테스트 통과만으로 판정하지 않았다. 아래 근거는 수익성 승인이나 운영 배포 승인이 아니다.

## 요구사항 대조

| 요구사항 | 확인한 근거 | 판단 |
|---|---|---|
| 문제 당시 기록, 현재 소스, 현재 EXE, 감사 시 실행 상태 구분 | `runtime-audit.md`는 네 상태를 별도로 기록한다. 현재 EXE의 최소매수 분기가 남아 있으며 설치 GUI의 저장값이 true인 점, 감사 시 실행 프로세스가 없고 예약 작업이 Disabled인 점을 구분한다. 9/23 사건은 현 EXE 생성보다 앞서므로 현 hash로 확정 귀속하지 않는다. | 충족 |
| 현행 일일 최소매수와 폐기된 강제매수 플래그 구분 | 현재 호출 경로는 `daily_buy_due` → 선정 적격성 → `daily_minimum_decision`이다. `daily_forced_order_enabled`를 되살리지 않았다. `test_entry_policy_engine.py`는 폐기 플래그 true/false 모두 최소매수 비활성 시 no_trade를 유지한다. | 충족 |
| 낮은 점수 매수 뒤 약 5분 후 일반 매도 재현 | 실제 `TradingEngine.run_once()` dry-run 경로에서 매수 점수 0, 정상 1% 예산보다 큰 위험거리, 최소매수 사유, 5분 뒤 동일 지표의 기술적 매도를 검사한다. 보유 상태는 명시적으로 메모리에서 주입하며 실제 체결이라 주장하지 않는다. `policy-replay.json`도 합성이라고 표시한다. | 충족 |
| B: 강제 진입 제거, 무거래 허용 | `EntryPolicyStrategy._entry_policy()` B는 원래 기술적 결정을 반환한다. 무보유·당일 0건·보유 1종목 상태를 검증한다. 목표 건수 충족을 위한 위험·가격·수량 완화는 없다. | 충족 |
| C: 동시 매수/매도 점수 충돌 거부 및 완성 봉 중복 억제 | 동일 입력 점수를 기록하고 매도 점수 기준 충족 시 신규 진입을 거부한다. 같은 봉·수정된 같은 봉·과거 봉은 새 일반 신호가 되지 않으며 더 늦은 완성 봉에서 해제된다. 미래/시차 없는 날짜 입력의 제한도 검사한다. | 충족 |
| C에서도 신선한 유효 평가가격의 하드 손절 유지 | 보호 판단을 중복 신호 제한보다 먼저 수행한다. 같은 봉의 새 mark, 미래 ATR 제외, 완성 봉이 없는 경우의 유효 mark 보호 테스트가 통과했다. 실제 분봉 C의 매도 2건 모두 `fixed_stop_loss`다. | 충족 |
| A/B/C 동일 엔진·청산·자금·위험·비용 | 모두 같은 `Backtester`, `MatchedEntryRisk`, `TechnicalStrategy` 청산을 공유한다. 3%/5%, 트레일링 2%/1%, ATR14×3/×5, `corrected_exits=false`, 일반 1%, 1주/최대 1주, $35, 단일·총 투자 50%, 현금 5%, 일일 2% 신규매수 중지를 유지한다. 최종 일봉·분봉 러너 모두 체결 시 총노출 재검사 .5를 전달하며 프로필 로더는 다른 값의 입력을 거부한다. | 충족 |
| A의 역사적 재현 한계와 실제 5% 예외 구분 | 프로필·protocol·manifest·정책 문서가 A를 동일 위험한도의 부분 재현으로 명시한다. 역사적 5% 예외와 학습 기반 동적 선정은 포함하지 않는다. 실제 소스 엔진 테스트는 5% 예외가 필요한 낮은 점수 진입 경로를 별도로 확인한다. | 충족 |
| 기존 8%/10%/진입 ATR 후보 보존 | 현 `experiments/early_exit/profiles.json`의 전체 candidates를 이전 `synthetic-smoke-final/protocol.json` candidates와 JSON 깊은 비교하여 일치를 확인했다. | 충족 |
| 실제 자료 수집, 누락을 미제공으로 오인하지 않기 | KIS 인증 성공과 조회 결과, Yahoo 519봉×4, ECB 환율 530행이 존재한다. 로컬 인증서 문제·과거 미수집 상태·응답에 없는 실제 체결시각/비용 필드를 각각 구분한다. | 충족 |
| 기업행위와 평가 구간 통제 | 사전 동결안 및 amendment, 실제 manifest가 CMCSA 기업행위 이후 2026-01-06부터 64봉 준비를 적용한다. 주 비교의 train/validation은 unavailable이며 final만 있다. KDP/HIVE·SPY 보충군은 기존 경계를 유지한다. | 충족 |
| 주문·취소·앱 실행·스케줄러/운영 설정 변경 금지 | 수집기 transport는 인증 POST와 고정 조회 GET만 허용하며 실거래 브로커/엔진을 import하지 않는다. 독립 비교 CLI는 socket·subprocess 접근을 차단한다. EXE·설정 hash가 감사 기준과 일치한다. 검토자는 앱·브로커·예약 작업을 실행하지 않았다. | 충족 |
| 개인 원장 비노출 | 원문은 저장소 밖 private run directory에 있다. 저장소 보고서는 집계·schema·제한사항만 사용한다. 검토자는 원문 행을 출력하지 않고 총 22행/22체결주문/매수11·매도11 집계만 대조했다. | 충족 |

## 실제 산출물과 해석 경계

- `actual-main/`: 기업행위 제외 후 각 종목 183봉, 준비기간 후 2026-04-09~09-28 final. base A/B/C 모두 USD 누적 -0.0225638%, 완결 거래 2건, 강제 진입 체결 0건이다. stress는 모두 0건이다. 이 결과로 B 또는 C의 수익 우위를 주장할 수 없다.
- `actual-no-action-pair/`: 원래 train/validation/final을 유지한다. final base A -0.1059095%, B/C -0.4393272%이고 13 대 5건이다. C가 언제나 수익을 개선한다는 해석에 반대되는 사례도 산출물에 남아 있다. 이 보충군을 CMCSA 포함 주 비교의 누락된 train/validation으로 바꾸어 부르면 안 된다.
- `actual-spy-control/`: 모든 구간·비용·정책에서 무거래다. 정수 1주 및 $35/노출 제한을 적용한 별도 대조이며, 전략 우수성이나 SPY 투자수익을 의미하지 않는다. USD 현금 무거래에서도 KRW 환율 평가손익은 달라진다.
- `intraday-actual-comparison/`: 2026-09-23/24/25/28 정규장 관측이다. base A/B는 USD -0.6707129%, C는 -0.4007021%다. A/B는 매수 9·매도 8, C는 매수·매도 각 2건이다. 평가액에는 A/B의 남은 포지션과 미실현손익이 포함된다. 다음 5분 격자 일반 매도는 A/B 각 5건, C 0건이며 C의 2건은 고정 손절이다. 강제 진입 체결은 이 짧은 실제 자료에서 모두 0건이다.
- 분봉 공급자의 라벨이 시작/종료 시각인지 확정되지 않아 명시적 +5분 가용 지연을 적용한다. 지표는 이전 거래일 완성 일봉이다. 당일 진행 일봉을 썼던 실제 운영, 당시 동적 선정·호가·개별 체결을 복원한 결과가 아니다. 월간 수익으로 외삽하지 않고 월별 수익/최악 월은 null이다.
- KIS 집계는 22개 체결주문, 매수11/매도11, 창 안에서 11개 닫힌 cycle, 매칭 총손익 -$1.083을 보고한다. 실제 체결시각과 비용이 관측 응답에 없으므로 순손익·정확한 보유시간을 확정하지 않는다. 이전 감사의 제출 성공 이벤트와 구분된다.
- 계좌 실제 수수료·매도 제비용·환전 비용·운영비는 검증되지 않았다. 배당 현금은 제외한다. 월 +10% 과거 빈도는 미래 확률이 아니며, 완전 달과 부분 관측 월을 따로 센다. 실제 비교에서 양의 지속 수익이나 월 +10% 보장 근거는 확보되지 않았다.

위 값은 각 디렉터리 `summary.csv`, `fills.csv`, `protocol.json`, `manifest.json`(분봉은 protocol 내 manifest)와 대조했다. 모든 실제 비교의 매수 행은 수량 1주이고 $35 초과 체결은 없었다. 일봉의 `literal_five_minute_exits`는 비어 있으며 일봉 결과를 5분 매도 증거로 사용하지 않는다.

## 독립 검증 증거

실행 명령:

```text
python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_entry_policy_strategy.py tests/test_entry_policy_engine.py tests/test_entry_policy_fills.py tests/test_entry_comparison_limits.py tests/test_entry_comparison_metrics.py tests/test_entry_comparison_cli.py tests/test_entry_intraday_replay.py tests/test_research_readonly.py tests/test_research_readonly_collect.py tests/test_research_readonly_boundaries.py tests/test_research_public.py
97 passed in 12.21s
```

이후 병행 검토에서 보완한 경계만 새 상태로 재검증했다. 아래 55개와 위 97개는 중복되므로 합산하지 않는다.

```text
python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_entry_fill_exposure.py tests/test_entry_comparison_cli.py tests/test_entry_intraday_replay.py tests/test_research_readonly_boundaries.py tests/test_research_public.py
55 passed in 10.53s
```

직접 소스를 다시 읽어 비교 CLI·라이브러리·공개 수집기·분봉 출력이 protocol 유무와 무관하게 비어 있지 않은 디렉터리를 거부함을 확인했다. dotenv 내부 마지막 중복 키와 파일 간 우선순위가 GUI 규칙에 맞게 처리된다. 최종 [보안 검토](review-security.md)도 동일 결함의 독립 재현을 통해 PASS를 기록했다.

다음 읽기 검증도 별도로 수행했다.

1. 공개 종목별 CSV 4개는 각각 519행이며 공개 manifest의 SHA-256과 일치한다. KIS canonical 5Min CSV 3개도 최종 수집 summary의 hash와 일치한다.
2. 이전 early-exit 최종 hash 목록과 `engine_cycle.py`, `strategy.py`, `strategy_config.py`, `exit_experiment_metrics.py`, `run_exit_experiments.py`, `run_offline_tests.py`가 일치함을 확인했다. 공통 `backtest.py`·`backtest_execution.py`는 최초 검토 후 선택적 체결 시 총노출 검사가 추가됐으므로 이전 hash 보존 대상이라고 부르지 않는다. 기존 호출의 기본값은 None이고 신규 일봉·분봉 비교에서만 .5로 연결한다.
3. 현재 EXE SHA-256은 `b34486f790bc45d0f6e73189999f197760c77da482c20dd1a14b94d768617cea`이다. 인접 KIS config, LocalAppData GUI config, 루트 GUI config도 `runtime-audit.md`의 hash와 일치한다. 정적 bytecode/과거 배포 연결의 세부 결론은 해당 감사 문서의 방법과 한계에 근거하며 이 검토에서 EXE를 실행해 재현하지 않았다.
4. 기존 실제 결과는 체결 시 검사 추가 전 생성본을 보존한다. [코드 검토의 Independent runtime evidence](review-code.md)는 48개 시나리오·276개 체결을 시간순으로 대사했다. 모든 체결은 HIVE이고 매수 시 보유는 0, 수량·동시보유 위반은 없으며 최종 현금 오차는 $0이다. 각 매수의 `price×qty/(매수 전 현금−신규 수수료)`로 재계산한 정확한 체결 노출 최대값은 주 비교 4.4592279934%, 보조군 5.1626810502%, 분봉 5.9462818473%, SPY 0이다. 새 50% 검사의 거절 조건에 닿지 않는 불변식 증거와 새 경계 회귀를 검토했으므로 동일 성과 실험을 다시 돌리거나 원래 결과를 덮어쓸 필요는 없다. 종가 기준 분봉 최대 5.938303%와 체결 시점 최대값은 구분한다.

## 구조적 반론 6개

| 질문 | 결론 |
|---|---|
| 진입 문제를 손절폭 확대의 효과로 바꾸었는가? | 아니다. 새 비교의 청산 숫자는 모두 고정하며 이전 넓은 손절 후보는 분리 보존했다. |
| 목표 매수 건수를 성과나 체결로 취급하는가? | 아니다. 실제 fill 콜백으로만 목적 수량을 누적하고 승인/거절/미체결은 구분한다. |
| A를 실제 과거 운용 전체와 같다고 주장하는가? | 아니다. 5% 위험 예외와 동적 선정 생략을 명시하고 실제 엔진 경로 검증을 분리했다. |
| 데이터 한계를 결과를 본 뒤 유리하게 조정했는가? | 저장된 사전안·기업행위 amendment와 실제 출력이 일관된다. 후속으로 경계를 옮기거나 더 좋은 구간을 선택한 근거는 발견하지 못했다. 시간 순서 자체에 대한 독립 서명은 없으므로 파일 내용만으로 외부의 사전등록 수준을 주장하지 않는다. |
| 무거래/수익 미실현으로 손실을 숨기는가? | 아니다. USD/KRW 평가액, 미실현손익, 무거래 상태, 완전 달 수가 따로 남는다. |
| 보수적 C가 모든 위험과 수익성을 해결하는가? | 아니다. 실제 분봉에서 C도 손절 손실이 났고 일봉 보충 final에서는 A보다 결과가 낮다. 운영 신선도·재시작 장부·실제 비용·표본 확장은 별도 과제로 남는다. |

검토 범위 밖: 실거래 적용, 스케줄러 재시작, EXE 재빌드/교체, 실제 계좌 주문/취소, 당시 모든 체결의 정확한 시장상태 재구성, 미래 수익 보장.
